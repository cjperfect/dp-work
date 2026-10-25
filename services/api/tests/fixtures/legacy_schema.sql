-- 旧库基线结构快照（仅用于迁移兼容性测试输入）
-- 模拟已具备最终用户表结构、但没有 Alembic 版本号的旧库，
-- 供 test_migrations.py 的旧库接入基线测试使用。
-- 触发器函数属于迁移内容，旧库快照不包含；新环境建表一律走 migrations。

CREATE TABLE users (
username text NOT NULL,
password_hash text NOT NULL,
department text NOT NULL,
role text DEFAULT 'member'::text NOT NULL,
status smallint DEFAULT 0 NOT NULL,
created_at timestamp with time zone DEFAULT now() NOT NULL,
id bigint NOT NULL,
updated_at timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE users ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
SEQUENCE NAME users_id_seq
START WITH 1
INCREMENT BY 1
NO MINVALUE
NO MAXVALUE
CACHE 1
);
ALTER TABLE ONLY users
ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY users
ADD CONSTRAINT users_username_key UNIQUE (username);
