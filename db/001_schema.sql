CREATE TABLE tenants (
    id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE
);

CREATE TABLE users (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    email     text NOT NULL UNIQUE,
    role      text NOT NULL CHECK (role IN ('viewer', 'engineer', 'admin')),
    UNIQUE (tenant_id, id)
);

CREATE TABLE projects (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    name      text NOT NULL,
    UNIQUE (tenant_id, id)
);

CREATE TABLE documents (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    project_id uuid NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('drawing', 'inspection_report', 'specification')),
    title      text NOT NULL,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id)
);

CREATE TABLE revisions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    document_id uuid NOT NULL,
    rev         text NOT NULL,
    status      text NOT NULL CHECK (status IN ('draft', 'in_review', 'approved', 'superseded')),
    approved_by uuid,
    approved_at timestamptz,
    file_path   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, rev),
    CHECK (status NOT IN ('approved', 'superseded') OR approved_at IS NOT NULL),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id),
    FOREIGN KEY (tenant_id, approved_by) REFERENCES users (tenant_id, id)
);

CREATE INDEX documents_tenant_project_idx ON documents (tenant_id, project_id);
CREATE INDEX revisions_latest_approved_idx
    ON revisions (document_id, approved_at DESC) WHERE status = 'approved';