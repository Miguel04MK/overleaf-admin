// =============================================================
// Seed idempotente para MongoDB de Overleaf CE
// 12 usuarios (admins, profesores, alumnos, investigadores) + 12 proyectos
//
// Uso:
//   docker cp scripts/seed_overleaf.js mongo:/tmp/seed.js
//   docker exec mongo mongosh --quiet /tmp/seed.js
//
// Es idempotente: si detecta >= 10 usuarios ya cargados no reinserta.
// =============================================================
const db = db.getSiblingDB('sharelatex');

const existingUsers = db.users.countDocuments({});
if (existingUsers >= 10) {
  print('Seed skipped: ' + existingUsers + ' users already present.');
  quit();
}

db.users.deleteMany({});
db.projects.deleteMany({});

function oid() { return new ObjectId(); }
function daysAgo(n) { return new Date(Date.now() - n * 86400000); }
function mkFolder(name, docs, folders) {
  return { _id: oid(), name: name, docs: docs || [], folders: folders || [], fileRefs: [] };
}
function mkDoc(name, lines) { return { _id: oid(), name: name, lines: lines || 10 }; }

const users = [
  { email: 'admin@overleaf.local', first_name: 'Super', last_name: 'Admin', isAdmin: true, quotaBytes: 5368709120, signUpDate: daysAgo(400), lastLoggedIn: daysAgo(1) },
  { email: 'sysadmin@uni.es', first_name: 'Maria', last_name: 'Gestora', isAdmin: true, quotaBytes: 5368709120, signUpDate: daysAgo(350), lastLoggedIn: daysAgo(2) },
  { email: 'prof.garcia@uni.es', first_name: 'Antonio', last_name: 'Garcia', isAdmin: false, quotaBytes: 3221225472, signUpDate: daysAgo(300), lastLoggedIn: daysAgo(1) },
  { email: 'prof.martinez@uni.es', first_name: 'Laura', last_name: 'Martinez', isAdmin: false, quotaBytes: 3221225472, signUpDate: daysAgo(280), lastLoggedIn: daysAgo(3) },
  { email: 'alumno1@uni.es', first_name: 'Miguel', last_name: 'Lopez Ruiz', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(200), lastLoggedIn: daysAgo(1) },
  { email: 'alumno2@uni.es', first_name: 'Sara', last_name: 'Fernandez Gil', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(180), lastLoggedIn: daysAgo(5) },
  { email: 'alumno3@uni.es', first_name: 'Carlos', last_name: 'Sanchez', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(160), lastLoggedIn: daysAgo(2) },
  { email: 'alumno4@uni.es', first_name: 'Ana', last_name: 'Perez Moreno', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(140), lastLoggedIn: daysAgo(10) },
  { email: 'alumno5@uni.es', first_name: 'Diego', last_name: 'Romero', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(120), lastLoggedIn: daysAgo(1) },
  { email: 'alumno6@uni.es', first_name: 'Elena', last_name: 'Navarro', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(100), lastLoggedIn: daysAgo(30) },
  { email: 'alumno7@uni.es', first_name: 'Pablo', last_name: 'Torres Vega', isAdmin: false, quotaBytes: 1073741824, signUpDate: daysAgo(80), lastLoggedIn: daysAgo(0) },
  { email: 'investigador1@uni.es', first_name: 'Rosa', last_name: 'Jimenez', isAdmin: false, quotaBytes: 2147483648, signUpDate: daysAgo(500), lastLoggedIn: daysAgo(7) },
  { email: 'investigador2@uni.es', first_name: 'Javier', last_name: 'Ortega', isAdmin: false, quotaBytes: 2147483648, signUpDate: daysAgo(450), lastLoggedIn: daysAgo(4) },
];

const userIds = [];
users.forEach(u => {
  const _id = oid();
  userIds.push(_id);
  db.users.insertOne({
    _id: _id,
    email: u.email,
    first_name: u.first_name,
    last_name: u.last_name,
    isAdmin: u.isAdmin,
    features: { collaborators: -1, versioning: true, compileTimeout: 180, compileGroup: 'standard' },
    featuresOverride: { quotaBytes: u.quotaBytes },
    signUpDate: u.signUpDate,
    lastLoggedIn: u.lastLoggedIn,
    hashedPassword: '$2a$10$abcdefghijklmnopqrstuuNvqV9zHn8VQfx0sL1pZ2yq9XeP6n1vSC',
    emails: [{ email: u.email, reversedHostname: u.email.split('@')[1].split('').reverse().join('') }],
  });
});

const projects = [
  { name: 'TFG - Sistema de Gestion Overleaf', ownerIdx: 4, collaborators: [2], readOnly: [], subfolders: ['capitulos', 'imagenes', 'bibliografia'], docs: ['main.tex', 'intro.tex', 'estado-arte.tex', 'disenio.tex', 'conclusiones.tex'] },
  { name: 'TFG - App Android para Alumnos', ownerIdx: 5, collaborators: [2, 3], readOnly: [], subfolders: ['cap', 'img'], docs: ['main.tex', 'memoria.tex'] },
  { name: 'TFG - Analisis de Redes Sociales', ownerIdx: 6, collaborators: [3], readOnly: [], subfolders: ['src'], docs: ['main.tex', 'bibliografia.bib'] },
  { name: 'TFG - Machine Learning en Educacion', ownerIdx: 7, collaborators: [2], readOnly: [11, 12], subfolders: [], docs: ['main.tex'] },
  { name: 'TFG - Seguridad en IoT', ownerIdx: 8, collaborators: [3], readOnly: [], subfolders: ['figuras'], docs: ['main.tex', 'cap1.tex'] },
  { name: 'TFM - Blockchain aplicado a actas', ownerIdx: 11, collaborators: [2, 3], readOnly: [], subfolders: ['capitulos', 'codigo'], docs: ['main.tex', 'metodologia.tex', 'resultados.tex'] },
  { name: 'Articulo - Deep Learning for Fisheries', ownerIdx: 11, collaborators: [12, 2], readOnly: [], subfolders: ['figures'], docs: ['paper.tex', 'refs.bib'] },
  { name: 'Articulo - Network Analysis 2026', ownerIdx: 12, collaborators: [11], readOnly: [3], subfolders: [], docs: ['paper.tex'] },
  { name: 'Practica 3 - Sistemas Operativos', ownerIdx: 9, collaborators: [], readOnly: [], subfolders: [], docs: ['main.tex'] },
  { name: 'Practica Final - Compiladores', ownerIdx: 10, collaborators: [4, 5], readOnly: [], subfolders: [], docs: ['main.tex'] },
  { name: 'Plantilla TFG Facultad Informatica', ownerIdx: 2, collaborators: [3], readOnly: [4, 5, 6, 7, 8], subfolders: ['ejemplos'], docs: ['template.tex', 'README.tex'] },
  { name: 'Apuntes Algebra Lineal 2026', ownerIdx: 3, collaborators: [], readOnly: [4, 5, 6], subfolders: ['temas'], docs: ['apuntes.tex'] },
];

projects.forEach(p => {
  const ownerId = userIds[p.ownerIdx];
  const rootFolder = mkFolder('rootFolder');
  rootFolder.docs = p.docs.map(d => mkDoc(d, 50 + Math.floor(Math.random() * 200)));
  rootFolder.folders = p.subfolders.map(s => mkFolder(s, [mkDoc(s + '-1.tex', 30), mkDoc(s + '-2.tex', 40)]));
  const members = p.collaborators.map(i => userIds[i]);
  const readOnlyMembers = p.readOnly.map(i => userIds[i]);
  db.projects.insertOne({
    _id: oid(),
    name: p.name,
    owner_ref: ownerId,
    collaberator_refs: members,
    readOnly_refs: readOnlyMembers,
    tokenAccessReadAndWrite_refs: [],
    tokenAccessReadOnly_refs: [],
    publicAccesLevel: 'private',
    lastUpdated: daysAgo(Math.floor(Math.random() * 30)),
    lastOpened: daysAgo(Math.floor(Math.random() * 20)),
    rootFolder: [rootFolder],
    compiler: 'pdflatex',
    spellCheckLanguage: 'es',
    version: Math.floor(Math.random() * 100) + 10,
  });
});

print('=== SEED COMPLETE ===');
print('Users: ' + db.users.countDocuments({}));
print('Projects: ' + db.projects.countDocuments({}));
