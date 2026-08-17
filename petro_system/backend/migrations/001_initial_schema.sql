CREATE TABLE IF NOT EXISTS rule_categories (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    knowledge_type TEXT NOT NULL,
    display_order INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO rule_categories (code, name, knowledge_type, display_order) VALUES
    ('SOP', '操作规程规则', '操作规程类', 1),
    ('QS', '质量标准规则', '质量标准类', 2),
    ('FLOW', '流程特征规则', '流程特征类', 3),
    ('PROC', '工艺规范规则', '工艺规范类', 4),
    ('EXP', '调度经验规则', '调度经验类', 5);

CREATE TABLE IF NOT EXISTS source_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL UNIQUE,
    file_path TEXT,
    file_sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_name TEXT NOT NULL,
    source_file_path TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'conflict')),
    expected_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_no INTEGER NOT NULL,
    rule_no TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL,
    category_code TEXT NOT NULL REFERENCES rule_categories(code),
    knowledge_type TEXT NOT NULL,
    subtype TEXT NOT NULL,
    applicable_scope TEXT NOT NULL,
    trigger_condition TEXT,
    rule_content TEXT NOT NULL,
    parameter_text TEXT,
    source_document_id INTEGER NOT NULL REFERENCES source_documents(id),
    source_page TEXT NOT NULL,
    source_basis TEXT NOT NULL,
    notes TEXT,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'published'
        CHECK (status IN ('draft', 'published', 'archived')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS rule_change_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rules(id),
    import_batch_id INTEGER REFERENCES import_batches(id),
    action TEXT NOT NULL CHECK (action IN ('insert', 'update', 'archive', 'restore')),
    old_values TEXT,
    new_values TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rules_category ON rules(category_code);
CREATE INDEX IF NOT EXISTS idx_rules_name ON rules(rule_name);
CREATE INDEX IF NOT EXISTS idx_rules_subtype ON rules(subtype);
CREATE INDEX IF NOT EXISTS idx_rules_source_document ON rules(source_document_id);
CREATE INDEX IF NOT EXISTS idx_rules_status ON rules(status, deleted_at);
CREATE INDEX IF NOT EXISTS idx_import_batches_hash ON import_batches(source_file_sha256);
CREATE INDEX IF NOT EXISTS idx_change_logs_rule ON rule_change_logs(rule_id, created_at);
