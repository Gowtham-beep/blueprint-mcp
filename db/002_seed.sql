INSERT INTO tenants (name) VALUES ('Acme Steel'), ('Birla Fab');

INSERT INTO users (tenant_id, email, role)
SELECT t.id, u.email, u.role FROM tenants t
JOIN (VALUES ('Acme Steel','alice@acme.test','engineer'),
             ('Acme Steel','vik@acme.test','viewer'),
             ('Birla Fab','bob@birla.test','engineer')) AS u(tname,email,role)
  ON u.tname = t.name;

INSERT INTO projects (tenant_id, name)
SELECT id, 'Project A' FROM tenants;

INSERT INTO documents (tenant_id, project_id, kind, title)
SELECT p.tenant_id, p.id, 'drawing', 'Main frame GA drawing' FROM projects p;

INSERT INTO revisions (tenant_id, document_id, rev, status, approved_by, approved_at, created_at, file_path)
SELECT d.tenant_id, d.id, 'A', 'superseded',
       (SELECT id FROM users u WHERE u.tenant_id = d.tenant_id AND u.role='engineer'),
       now() - interval '30 days', now() - interval '30 days', 'docs/' || d.id || '_A.pdf' FROM documents d
UNION ALL
SELECT d.tenant_id, d.id, 'B', 'approved',
       (SELECT id FROM users u WHERE u.tenant_id = d.tenant_id AND u.role='engineer'),
       now() - interval '5 days', now() - interval '5 days', 'docs/' || d.id || '_B.pdf' FROM documents d
UNION ALL
SELECT d.tenant_id, d.id, 'C', 'draft', NULL, NULL, now(), 'docs/' || d.id || '_C.pdf' FROM documents d;