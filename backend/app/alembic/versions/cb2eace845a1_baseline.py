"""baseline

Revision ID: cb2eace845a1
Revises: 
Create Date: 2026-05-25 04:31:10.496178

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "cb2eace845a1"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(sa.text("""CREATE EXTENSION IF NOT EXISTS vector"""))
    op.execute(sa.text("""CREATE TABLE agent_activities (
	thread_id VARCHAR(255) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	main_goal TEXT NOT NULL, 
	artifacts_json TEXT NOT NULL, 
	agent_state_json TEXT NOT NULL, 
	active_memories_json TEXT NOT NULL, 
	human_request_json TEXT, 
	final_outcome TEXT NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (thread_id)
)"""))
    op.execute(sa.text("""CREATE TABLE checkpoint_blobs (
	thread_id TEXT NOT NULL, 
	checkpoint_ns TEXT NOT NULL, 
	channel TEXT NOT NULL, 
	version TEXT NOT NULL, 
	type TEXT NOT NULL, 
	blob BYTEA, 
	PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
)"""))
    op.execute(sa.text("""CREATE TABLE checkpoint_migrations (
	v SERIAL NOT NULL, 
	PRIMARY KEY (v)
)"""))
    op.execute(sa.text("""CREATE TABLE checkpoint_writes (
	thread_id TEXT NOT NULL, 
	checkpoint_ns TEXT NOT NULL, 
	checkpoint_id TEXT NOT NULL, 
	task_id TEXT NOT NULL, 
	idx INTEGER NOT NULL, 
	channel TEXT NOT NULL, 
	type TEXT, 
	blob BYTEA NOT NULL, 
	task_path TEXT NOT NULL, 
	PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
)"""))
    op.execute(sa.text("""CREATE TABLE checkpoints (
	thread_id TEXT NOT NULL, 
	checkpoint_ns TEXT NOT NULL, 
	checkpoint_id TEXT NOT NULL, 
	parent_checkpoint_id TEXT, 
	type TEXT, 
	checkpoint JSON NOT NULL, 
	metadata JSON NOT NULL, 
	PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
)"""))
    op.execute(sa.text("""CREATE TABLE citations (
	id SERIAL NOT NULL, 
	doc_id VARCHAR(1024) NOT NULL, 
	doc_path VARCHAR(1024) NOT NULL, 
	tool_used VARCHAR(50) NOT NULL, 
	session_id VARCHAR(255), 
	agent_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_citations_doc_id ON citations (doc_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_citations_session_id ON citations (session_id)"""))
    op.execute(sa.text("""CREATE TABLE conversations (
	id VARCHAR(255) NOT NULL, 
	project_id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	title VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	sync_status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	last_synced_at TIMESTAMP WITH TIME ZONE, 
	is_pinned BOOLEAN DEFAULT '0' NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_conversations_is_pinned ON conversations (is_pinned)"""))
    op.execute(sa.text("""CREATE INDEX ix_conversations_project_id ON conversations (project_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_conversations_member_id ON conversations (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_conversations_sync_status ON conversations (sync_status)"""))
    op.execute(sa.text("""CREATE TABLE doc_stats (
	doc_id VARCHAR(1024) NOT NULL, 
	doc_path VARCHAR(1024) NOT NULL, 
	total_citations INTEGER NOT NULL, 
	unique_sessions INTEGER NOT NULL, 
	last_accessed TIMESTAMP WITH TIME ZONE, 
	tools_used TEXT, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (doc_id)
)"""))
    op.execute(sa.text("""CREATE TABLE file_operations (
	id SERIAL NOT NULL, 
	thread_id VARCHAR(255) NOT NULL, 
	message_id VARCHAR(36), 
	run_id VARCHAR(36), 
	file_path TEXT NOT NULL, 
	operation VARCHAR(20) NOT NULL, 
	diff_content TEXT, 
	original_content TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_file_operations_run_id ON file_operations (run_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_file_operations_message_id ON file_operations (message_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_file_operations_thread_id ON file_operations (thread_id)"""))
    op.execute(sa.text("""CREATE TABLE human_requests (
	id VARCHAR(36) NOT NULL, 
	thread_id VARCHAR(36) NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	description TEXT NOT NULL, 
	options JSON, 
	context TEXT, 
	default_value VARCHAR(255), 
	status VARCHAR(50) NOT NULL, 
	result TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_human_requests_thread_id ON human_requests (thread_id)"""))
    op.execute(sa.text("""CREATE TABLE jobs (
	id SERIAL NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	payload TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	error TEXT, 
	result TEXT, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_jobs_status ON jobs (status)"""))
    op.execute(sa.text("""CREATE INDEX ix_jobs_type ON jobs (type)"""))
    op.execute(sa.text("""CREATE TABLE learned_skills (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	trigger_patterns JSON NOT NULL, 
	namespace VARCHAR(500), 
	parameters JSON NOT NULL, 
	preconditions JSON, 
	instructions TEXT, 
	tools_used JSON, 
	source_thread_id VARCHAR(255), 
	source_session_id VARCHAR(255), 
	success_count INTEGER NOT NULL, 
	failure_count INTEGER NOT NULL, 
	confidence_score FLOAT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	last_success_at TIMESTAMP WITH TIME ZONE, 
	last_failure_at TIMESTAMP WITH TIME ZONE, 
	promotion_history TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	project_id INTEGER, 
	member_id INTEGER NOT NULL, 
	resource_path VARCHAR(500), 
	validation_report JSON, 
	skill_level VARCHAR(10), 
	skill_source VARCHAR(20), 
	execution_mode VARCHAR(20) NOT NULL, 
	macro_script TEXT, 
	allow_self_healing BOOLEAN NOT NULL, 
	active_model VARCHAR(100), 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_learned_skills_member_id ON learned_skills (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_learned_skills_namespace ON learned_skills (namespace)"""))
    op.execute(sa.text("""CREATE UNIQUE INDEX ix_learned_skills_name ON learned_skills (name)"""))
    op.execute(sa.text("""CREATE INDEX ix_learned_skills_project_id ON learned_skills (project_id)"""))
    op.execute(sa.text("""CREATE TABLE maintenance_reports (
	id SERIAL NOT NULL, 
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	level VARCHAR(50), 
	dry_run BOOLEAN, 
	duration_seconds FLOAT, 
	summary_json TEXT, 
	report_json TEXT, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_maintenance_reports_timestamp ON maintenance_reports (timestamp)"""))
    op.execute(sa.text("""CREATE TABLE mcp_servers (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	command VARCHAR(1024) NOT NULL, 
	args TEXT NOT NULL, 
	env TEXT NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE UNIQUE INDEX ix_mcp_servers_name ON mcp_servers (name)"""))
    op.execute(sa.text("""CREATE TABLE memory_concepts (
	id SERIAL NOT NULL, 
	project_id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	related_files JSON, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_memory_concepts_project_id ON memory_concepts (project_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_memory_concepts_member_id ON memory_concepts (member_id)"""))
    op.execute(sa.text("""CREATE TABLE messages (
	id VARCHAR(36) NOT NULL, 
	thread_id VARCHAR(255) NOT NULL, 
	member_id INTEGER NOT NULL, 
	project_id INTEGER, 
	role VARCHAR(50) NOT NULL, 
	content TEXT NOT NULL, 
	meta_data JSON, 
	thinking TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	sequence_number INTEGER, 
	checkpoint_id VARCHAR(255), 
	tool_calls JSON, 
	action_type VARCHAR(50) DEFAULT 'text' NOT NULL, 
	category VARCHAR(50), 
	content_type VARCHAR(50), 
	is_visible BOOLEAN DEFAULT '1' NOT NULL, 
	run_id VARCHAR(255), 
	status VARCHAR(50), 
	parent_id VARCHAR(36), 
	tool_call_id VARCHAR(255), 
	tool_name VARCHAR(255), 
	sync_status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	last_synced_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES messages (id), 
	CONSTRAINT uq_message_thread_seq UNIQUE (thread_id, sequence_number)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_member_id ON messages (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_sync_status ON messages (sync_status)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_content ON messages (content)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_project_id ON messages (project_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_category ON messages (category)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_run_id ON messages (run_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_tool_call_id ON messages (tool_call_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_thread_visible_id ON messages (thread_id, is_visible, id)"""))
    op.execute(sa.text("""CREATE INDEX ix_messages_thread_id ON messages (thread_id)"""))
    op.execute(sa.text("""ALTER TABLE messages ADD FOREIGN KEY(parent_id) REFERENCES messages (id)"""))
    op.execute(sa.text("""CREATE TABLE project_resources (
	id SERIAL NOT NULL, 
	project_id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	content TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_project_resources_project_id ON project_resources (project_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_project_resources_member_id ON project_resources (member_id)"""))
    op.execute(sa.text("""CREATE TABLE project_tasks (
	id VARCHAR(36) NOT NULL, 
	analysis_id VARCHAR(36), 
	project_id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	evocloud_task_id INTEGER, 
	parent_id VARCHAR(36), 
	status VARCHAR(50) NOT NULL, 
	progress INTEGER NOT NULL, 
	task_data JSON NOT NULL, 
	sync_status VARCHAR(50) NOT NULL, 
	sync_error TEXT, 
	synced_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES project_tasks (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_project_tasks_project_id ON project_tasks (project_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_project_tasks_member_id ON project_tasks (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_project_tasks_parent_id ON project_tasks (parent_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_project_tasks_analysis_id ON project_tasks (analysis_id)"""))
    op.execute(sa.text("""ALTER TABLE project_tasks ADD FOREIGN KEY(parent_id) REFERENCES project_tasks (id)"""))
    op.execute(sa.text("""CREATE TABLE repositories (
	id SERIAL NOT NULL, 
	project_id INTEGER, 
	member_id INTEGER NOT NULL, 
	sync_status VARCHAR(50) NOT NULL, 
	indexing_status VARCHAR(50) NOT NULL, 
	last_indexed_at TIMESTAMP WITH TIME ZONE, 
	detected_at TIMESTAMP WITH TIME ZONE, 
	imported_at TIMESTAMP WITH TIME ZONE, 
	name VARCHAR(255) NOT NULL, 
	url VARCHAR(1024) NOT NULL, 
	local_path VARCHAR(1024), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_repositories_project_id ON repositories (project_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_repositories_member_id ON repositories (member_id)"""))
    op.execute(sa.text("""CREATE TABLE router_training_data (
	id SERIAL NOT NULL, 
	instruction TEXT NOT NULL, 
	intent VARCHAR(50) NOT NULL, 
	reasoning TEXT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	source VARCHAR(50) NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE TABLE session_docs (
	session_id VARCHAR(255) NOT NULL, 
	doc_id VARCHAR(1024) NOT NULL, 
	accessed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (session_id, doc_id)
)"""))
    op.execute(sa.text("""CREATE TABLE synthesis_jobs (
	id SERIAL NOT NULL, 
	session_id VARCHAR(255) NOT NULL, 
	thread_id VARCHAR(255), 
	member_id INTEGER NOT NULL, 
	task_goal TEXT NOT NULL, 
	annotation_ids JSON NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	progress_percent INTEGER NOT NULL, 
	current_phase VARCHAR(100), 
	phase_analysis JSON, 
	keyframes JSON, 
	frame_analyses JSON, 
	extracted_insights JSON, 
	error_message TEXT, 
	error_traceback TEXT, 
	generated_skill JSON, 
	skill_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_synthesis_jobs_session_id ON synthesis_jobs (session_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_synthesis_jobs_thread_id ON synthesis_jobs (thread_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_synthesis_jobs_member_id ON synthesis_jobs (member_id)"""))
    op.execute(sa.text("""CREATE TABLE systemconfig (
	key VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	description VARCHAR, 
	PRIMARY KEY (key)
)"""))
    op.execute(sa.text("""CREATE TABLE thread_sequences (
	thread_id VARCHAR(255) NOT NULL, 
	next_seq INTEGER NOT NULL, 
	PRIMARY KEY (thread_id)
)"""))
    op.execute(sa.text("""CREATE TABLE todos (
	id VARCHAR(36) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	status todostatus NOT NULL, 
	priority todopriority NOT NULL, 
	category VARCHAR(50), 
	due_date TIMESTAMP WITH TIME ZONE, 
	source_conversation_id VARCHAR(255), 
	source_message_id VARCHAR(36), 
	run_id VARCHAR(36), 
	project_id INTEGER, 
	member_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_todos_run_id ON todos (run_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_todos_member_id ON todos (member_id)"""))
    op.execute(sa.text("""CREATE TABLE tools (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	signature TEXT NOT NULL, 
	category VARCHAR(100), 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE UNIQUE INDEX ix_tools_name ON tools (name)"""))
    op.execute(sa.text("""CREATE INDEX ix_tools_category ON tools (category)"""))
    op.execute(sa.text("""CREATE TABLE trace_events (
	id SERIAL NOT NULL, 
	thread_id VARCHAR(255) NOT NULL, 
	session_id VARCHAR(36), 
	run_id VARCHAR(36), 
	step_number INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	node_name VARCHAR(100) NOT NULL, 
	state_snapshot JSON, 
	event_type VARCHAR(50) NOT NULL, 
	payload JSON NOT NULL, 
	action_type VARCHAR(50), 
	action_payload TEXT, 
	is_human_action BOOLEAN NOT NULL, 
	source VARCHAR(20), 
	screenshot_path VARCHAR(500), 
	target_selector TEXT, 
	target_text TEXT, 
	reward FLOAT, 
	user_feedback TEXT, 
	recording_session_id VARCHAR(255), 
	timestamp FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	window_title TEXT, 
	app_name VARCHAR(255), 
	process_id INTEGER, 
	mouse_x INTEGER, 
	mouse_y INTEGER, 
	key_name VARCHAR(50), 
	mouse_button VARCHAR(20), 
	PRIMARY KEY (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_run_id ON trace_events (run_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_member_id ON trace_events (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_thread_id ON trace_events (thread_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_event_type ON trace_events (event_type)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_action_type ON trace_events (action_type)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_recording_session_id ON trace_events (recording_session_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_trace_events_session_id ON trace_events (session_id)"""))
    op.execute(sa.text("""CREATE TABLE wikipage (
	id SERIAL NOT NULL, 
	project_id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	title VARCHAR NOT NULL, 
	slug VARCHAR NOT NULL, 
	content TEXT, 
	parent_id INTEGER, 
	"order" INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES wikipage (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_wikipage_member_id ON wikipage (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_wikipage_slug ON wikipage (slug)"""))
    op.execute(sa.text("""CREATE INDEX ix_wikipage_project_id ON wikipage (project_id)"""))
    op.execute(sa.text("""ALTER TABLE wikipage ADD FOREIGN KEY(parent_id) REFERENCES wikipage (id)"""))
    op.execute(sa.text("""CREATE TABLE autonomous_tasks (
	id SERIAL NOT NULL, 
	intent_description TEXT NOT NULL, 
	project_id INTEGER, 
	member_id INTEGER NOT NULL, 
	skill_id INTEGER NOT NULL, 
	params_template JSON, 
	trigger_type VARCHAR(50) NOT NULL, 
	trigger_spec VARCHAR(255) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	consecutive_failures INTEGER NOT NULL, 
	max_retries INTEGER NOT NULL, 
	last_run_at TIMESTAMP WITH TIME ZONE, 
	next_run_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_failure_reason TEXT, 
	is_dead_letter BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(skill_id) REFERENCES learned_skills (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_autonomous_tasks_skill_id ON autonomous_tasks (skill_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_autonomous_tasks_member_id ON autonomous_tasks (member_id)"""))
    op.execute(sa.text("""CREATE INDEX ix_autonomous_tasks_next_run_at ON autonomous_tasks (next_run_at)"""))
    op.execute(sa.text("""CREATE INDEX ix_autonomous_tasks_project_id ON autonomous_tasks (project_id)"""))
    op.execute(sa.text("""ALTER TABLE autonomous_tasks ADD FOREIGN KEY(skill_id) REFERENCES learned_skills (id)"""))
    op.execute(sa.text("""CREATE TABLE message_references (
	id VARCHAR(36) NOT NULL, 
	message_id VARCHAR(36) NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	target_id VARCHAR(255) NOT NULL, 
	target_name VARCHAR(255) NOT NULL, 
	meta_data JSON, 
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(message_id) REFERENCES messages (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_message_references_message_id ON message_references (message_id)"""))
    op.execute(sa.text("""ALTER TABLE message_references ADD FOREIGN KEY(message_id) REFERENCES messages (id)"""))
    op.execute(sa.text("""CREATE TABLE plans (
	id VARCHAR(36) NOT NULL, 
	thread_id VARCHAR(255) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(thread_id) REFERENCES conversations (id)
)"""))
    op.execute(sa.text("""CREATE UNIQUE INDEX ix_plans_thread_id ON plans (thread_id)"""))
    op.execute(sa.text("""ALTER TABLE plans ADD FOREIGN KEY(thread_id) REFERENCES conversations (id)"""))
    op.execute(sa.text("""CREATE TABLE source_files (
	id SERIAL NOT NULL, 
	repository_id INTEGER NOT NULL, 
	path VARCHAR(1024) NOT NULL, 
	checksum VARCHAR(64) NOT NULL, 
	last_indexed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(repository_id) REFERENCES repositories (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_source_files_path ON source_files (path)"""))
    op.execute(sa.text("""ALTER TABLE source_files ADD FOREIGN KEY(repository_id) REFERENCES repositories (id)"""))
    op.execute(sa.text("""CREATE TABLE code_chunks (
	id SERIAL NOT NULL, 
	source_file_id INTEGER NOT NULL, 
	chunk_type VARCHAR(50) NOT NULL, 
	identifier VARCHAR(1024) NOT NULL, 
	start_line INTEGER NOT NULL, 
	end_line INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_file_id) REFERENCES source_files (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_code_chunks_source_file_id ON code_chunks (source_file_id)"""))
    op.execute(sa.text("""ALTER TABLE code_chunks ADD FOREIGN KEY(source_file_id) REFERENCES source_files (id)"""))
    op.execute(sa.text("""CREATE TABLE code_entities (
	id SERIAL NOT NULL, 
	file_id INTEGER NOT NULL, 
	name VARCHAR(1024) NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	full_name VARCHAR(1024) NOT NULL, 
	start_line INTEGER NOT NULL, 
	end_line INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(file_id) REFERENCES source_files (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_code_entities_name ON code_entities (name)"""))
    op.execute(sa.text("""CREATE INDEX ix_code_entities_full_name ON code_entities (full_name)"""))
    op.execute(sa.text("""ALTER TABLE code_entities ADD FOREIGN KEY(file_id) REFERENCES source_files (id)"""))
    op.execute(sa.text("""CREATE TABLE plan_steps (
	id VARCHAR(36) NOT NULL, 
	plan_id VARCHAR(36) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	status VARCHAR(50) NOT NULL, 
	result TEXT, 
	"order" INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	execution_run_id VARCHAR(255), 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES plans (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_plan_steps_plan_id ON plan_steps (plan_id)"""))
    op.execute(sa.text("""ALTER TABLE plan_steps ADD FOREIGN KEY(plan_id) REFERENCES plans (id)"""))
    op.execute(sa.text("""CREATE TABLE code_relations (
	id SERIAL NOT NULL, 
	source_entity_id INTEGER NOT NULL, 
	target_entity_id INTEGER, 
	target_name VARCHAR(1024), 
	relation_type VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(target_entity_id) REFERENCES code_entities (id), 
	FOREIGN KEY(source_entity_id) REFERENCES code_entities (id)
)"""))
    op.execute(sa.text("""CREATE INDEX ix_code_relations_target_name ON code_relations (target_name)"""))
    op.execute(sa.text("""ALTER TABLE code_relations ADD FOREIGN KEY(target_entity_id) REFERENCES code_entities (id)"""))
    op.execute(sa.text("""ALTER TABLE code_relations ADD FOREIGN KEY(source_entity_id) REFERENCES code_entities (id)"""))

def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS code_relations CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS plan_steps CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS code_entities CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS code_chunks CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS source_files CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS plans CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS message_references CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS autonomous_tasks CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS wikipage CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS trace_events CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS tools CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS todos CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS thread_sequences CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS systemconfig CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS synthesis_jobs CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS session_docs CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS router_training_data CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS repositories CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS project_tasks CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS project_resources CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS messages CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS memory_concepts CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS mcp_servers CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS maintenance_reports CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS learned_skills CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS jobs CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS human_requests CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS file_operations CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS doc_stats CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS conversations CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS citations CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoints CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoint_writes CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoint_migrations CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoint_blobs CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS agent_activities CASCADE"))
