"""
OverleafMongoAdapter — low-level MongoDB connection layer.

ISOLATION POINT: all MongoDB-specific logic lives here.
If Overleaf changes its MongoDB structure, only this file (and extractor.py)
needs updating. The rest of the platform is unaffected.

MongoDB version notes:
    - Overleaf CE 2.x / 3.x / 4.x / 5.x all use the 'sharelatex' database.
    - Collection names: 'users', 'projects' (stable across known versions).
    - Field names that MAY differ by version are documented in extractor.py.
"""
import logging
from contextlib import contextmanager

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)

# Default timeout for MongoDB connection attempts (seconds)
CONNECT_TIMEOUT_MS = 5000


class OverleafMongoAdapter:
    """
    Thin wrapper around a pymongo connection to Overleaf's MongoDB.

    Usage:
        adapter = OverleafMongoAdapter(uri="mongodb://localhost:27017/sharelatex")
        with adapter.get_db() as db:
            users = list(db["users"].find({}))
    """

    def __init__(self, uri: str, db_name: str = "sharelatex"):
        self.uri = uri
        self.db_name = db_name
        self._client: MongoClient | None = None

    def connect(self) -> None:
        """Open the MongoDB connection. Raises ConnectionFailure on error."""
        logger.info("Connecting to MongoDB at %s (db: %s)", self.uri, self.db_name)
        # directConnection=True bypasses replica-set discovery.
        # Overleaf CE runs MongoDB as a replica set with the Docker-internal
        # hostname 'mongo'. From outside Docker (Windows host / WSL host) that
        # hostname is not resolvable, so we connect directly to the exposed port
        # without letting pymongo re-resolve the replica-set member addresses.
        self._client = MongoClient(
            self.uri,
            serverSelectionTimeoutMS=CONNECT_TIMEOUT_MS,
            connectTimeoutMS=CONNECT_TIMEOUT_MS,
            directConnection=True,
        )
        # Force an actual connection attempt
        self._client.admin.command("ping")
        logger.info("MongoDB connection established.")

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            logger.info("MongoDB connection closed.")

    def is_connected(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    @contextmanager
    def get_db(self):
        """Context manager that yields the MongoDB database object."""
        if not self._client:
            self.connect()
        try:
            yield self._client[self.db_name]
        finally:
            pass  # Keep connection alive for the session; disconnect explicitly.

    def ping(self) -> bool:
        """Return True if MongoDB is reachable."""
        try:
            client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=CONNECT_TIMEOUT_MS,
                connectTimeoutMS=CONNECT_TIMEOUT_MS,
                directConnection=True,
            )
            client.admin.command("ping")
            client.close()
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as exc:
            logger.warning("MongoDB ping failed: %s", exc)
            return False


def make_adapter(app) -> OverleafMongoAdapter:
    """Factory: create adapter from Flask app config."""
    return OverleafMongoAdapter(
        uri=app.config["MONGO_URI"],
        db_name=app.config["MONGO_DB"],
    )
