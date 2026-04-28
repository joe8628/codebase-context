# Repo Map
# Generated: 2026-04-28T18:56:39  |  Files: 51  |  Symbols: 438
# Reference this in CLAUDE.md with: @.codebase-context/repo_map.md

---

## codebase_context/chunker.py
  + chunk_id(filepath: str, symbol_name: str, start_line: int) -> str:
  + build_chunks(symbols: list[Symbol], filepath: str) -> list[Chunk]:
  + _truncate_to_tokens(text: str, max_tokens: int) -> str:

## codebase_context/cli.py
  + _release_project_root() -> Path:
  + _setup_external_deps() -> None:
  + _setup_mcp_server(project_root: str) -> None:
  + _setup_memgram(project_root: str) -> None:
  + _write_session_protocol(project_root: str) -> None:
  + _update_gitignore(project_root: str) -> None:
  + _fetch_latest_release() -> tuple[str, str] | None:
  + _parse_version(v: str) -> tuple[int, ...]:

## codebase_context/db.py
  + get_connection(project_root: str, db_filename: str = "memory.db") -> sqlite3.Connection:

## codebase_context/embedder.py
  class Embedder:
    + __init__(self, model_name: str = EMBED_MODEL):
    + _seed_local_to_hf_cache(self, cache_dir: str, models_dir: str) -> bool:
    + _resolve_models_dir(self) -> str:
    + _get_model(self) -> "TextEmbedding":
    + embed(self, texts: list[str]) -> list[list[float]]:
    + embed_one(self, text: str) -> list[float]:

## codebase_context/indexer.py
  class Indexer:
    + __init__(self, project_root: str, embedder: EmbeddingProvider | None = None):
    + full_index(self, show_progress: bool = True) -> IndexStats:
    + incremental_index(self, show_progress: bool = True) -> IndexStats:
    + index_file(self, filepath: str) -> int:
    + remove_file(self, filepath: str) -> None:
    + _regenerate_repo_map(self) -> None:
  + discover_files(project_root: str) -> list[str]:

## codebase_context/mcp_server.py
  + _setup_logging(project_root: str) -> None:
  + run_server() -> None:
  + _run_server(server) -> None:
  + _handle_search(retriever, arguments: dict):
  + _handle_get_symbol(retriever, arguments: dict):
  + _handle_get_repo_map(retriever, project_root: str):
  + _handle_store_memory(memory_store, arguments: dict):
  + _handle_recall_memory(memory_store, arguments: dict):
  + _handle_record_change_manifest(memory_store, arguments: dict):
  + _handle_get_change_manifest(memory_store, arguments: dict):
  + _handle_lsp_tool(

## codebase_context/memory_store.py
  class MemoryStore:
    + __init__(self, project_root: str) -> None:
    + store_event(
    + search_events(
    + create_task(self, task_id: str, agent: str, payload: dict) -> None:
    + update_task_status(self, task_id: str, status: str) -> None:
    + get_task(self, task_id: str) -> dict | None:
    + list_tasks(self, status: str | None = None) -> list[dict]:
    + record_manifest(self, task_id: str, changes: list[dict]) -> int:
    + get_manifest(self, task_id: str) -> list[dict]:

## codebase_context/migrate.py
  class AlreadyMigratedError:
  + parse_handoff_blocks(text: str) -> list[dict]:
  + parse_decision_blocks(text: str) -> list[dict]:
  + run_migration(project_root: str) -> tuple[int, int]:

## codebase_context/parser.py
  class UnsupportedLanguageError:
  class LanguageHandler:
    + extract_docstring(self, node, source_bytes: bytes) -> str | None: ...
    + extra_nodes(self, node) -> list: ...
  class _DefaultHandler:
    + extract_docstring(self, node, source_bytes: bytes) -> str | None:
    + extra_nodes(self, node) -> list:
  class _PythonHandler:
    + extract_docstring(self, node, source_bytes: bytes) -> str | None:
    + extra_nodes(self, node) -> list:
  class _TypeScriptHandler:
    + extract_docstring(self, node, source_bytes: bytes) -> str | None:
    + extra_nodes(self, node) -> list:
  + _get_node_text(node, source_bytes: bytes) -> str:
  + extract_signature(
  + extract_calls(node, source_bytes: bytes) -> list[str]:
  + _extract_declarator_name(node, source_bytes: bytes) -> str | None:
  + _get_call_name(node, source_bytes: bytes) -> str | None:
  + _extract_class_methods(
  + parse_file(filepath: str) -> list[Symbol]:

## codebase_context/repo_map.py
  + generate_repo_map(project_root: str, symbols_by_file: dict[str, list[Symbol]]) -> str:
  + _params_from_sig(sig: str) -> str:
  + write_repo_map(project_root: str, repo_map: str) -> None:

## codebase_context/retriever.py
  class Retriever:
    + __init__(self, project_root: str, embedder: EmbeddingProvider | None = None):
    + search(
    + get_symbol(self, name: str) -> list[RetrievalResult]:
    + get_repo_map(self, project_root: str) -> str:
  + _search_result_to_retrieval(sr: SearchResult) -> RetrievalResult:

## codebase_context/store.py
  class VectorStore:
    + __init__(self, project_root: str):
    + _get_or_create_collection(self):
    + upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    + delete_by_filepath(self, filepath: str) -> None:
    + search(
    + get_by_symbol_name(self, name: str) -> list[SearchResult]:
    + count(self) -> int:
    + clear(self) -> None:

## codebase_context/utils.py
  + count_tokens(text: str) -> int:
  + slugify(text: str) -> str:
  + load_gitignore(project_root: str) -> pathspec.PathSpec:
  + is_ignored(filepath: str, project_root: str, gitignore: pathspec.PathSpec) -> bool:
  + find_project_root(start_path: str = ".") -> str:
  + load_index_meta(project_root: str):
  + load_symbols_cache(project_root: str) -> dict[str, list]:
  + save_symbols_cache(project_root: str, cache: dict[str, list]) -> None:
  + save_index_meta(project_root: str, meta) -> None:
  + format_results_for_agent(results: list) -> str:

## codebase_context/watcher.py
  class _CodebaseEventHandler:
    + __init__(self, indexer, project_root: str):
    + _should_handle(self, filepath: str) -> bool:
    + _schedule_flush(self) -> None:
    + _flush(self) -> None:
    + on_created(self, event):
    + on_modified(self, event):
    + on_deleted(self, event):
    + on_moved(self, event):
  + watch(project_root: str) -> None:
  + install_git_hook(project_root: str) -> None:
  + uninstall_git_hook(project_root: str) -> None:

## tests/test_chunker.py
  + make_symbol(name="my_func", sym_type="function", start=0, end=5,
  + test_chunk_has_context_prefix():
  + test_chunk_id_is_deterministic():
  + test_chunk_id_differs_for_different_inputs():
  + test_chunk_metadata_contains_required_fields():
  + test_long_chunk_truncated():
  + test_chunk_prefix_includes_parent_class():

## tests/test_cli.py
  class TestSetupMcpServer:
    + test_creates_settings_json_when_absent(self, tmp_project):
    + test_merges_into_existing_settings_json(self, tmp_project):
    + test_skips_if_entry_already_present(self, tmp_project):
    + test_confirmation_line_printed_on_accept(self, tmp_project):
    + test_skipped_when_user_declines(self, tmp_project):
    + test_invalid_json_in_existing_settings_treated_as_empty(self, tmp_project):
    + test_no_old_mcp_json_message(self, tmp_project):
  class TestSetupMemgram:
    + test_registers_ccindex_mem_serve(self, tmp_project):
    + test_memgram_mcp_entry_has_no_env(self, tmp_project):
    + test_skips_if_entry_already_present(self, tmp_project):
    + test_skips_when_user_declines(self, tmp_project):
  class TestSetupExternalDeps:
    + _which_except(self, *missing_binaries):
    + test_no_output_when_all_present(self, tmp_project):
    + test_installs_npm_lsp_on_accept(self, tmp_project):
    + test_shows_clangd_manual_instructions(self, tmp_project):
  class TestDoctorMemgram:
    + test_doctor_registers_memgram_when_missing(self, tmp_project):
    + test_doctor_skips_memgram_when_already_present(self, tmp_project):
    + test_doctor_skips_memgram_when_user_declines(self, tmp_project):

## tests/test_cli_lsp.py
  + _mock_indexer():
  + _init_project(tmp_path):
  + test_init_reports_missing_lsp_binaries(tmp_path):
  + test_init_skips_lsp_prompt_when_all_binaries_present(tmp_path):
  + test_init_npm_install_runs_on_confirm(tmp_path):
  + test_init_shows_clangd_manual_instructions_when_missing(tmp_path):

## tests/test_cli_version.py
  + test_version_flag_exits_0(runner):
  + test_version_flag_contains_version_string(runner):
  + _mock_github_response(tag: str, url: str = "https://github.com/joe8628/codebase-context/releases/tag/v2.0.0"):
  + test_fetch_latest_release_returns_tag_and_url():
  + test_fetch_latest_release_returns_none_on_network_error():
  + test_fetch_latest_release_returns_none_on_missing_tag():
  + test_parse_version_basic():
  + test_parse_version_strips_v_prefix():
  + test_parse_version_bad_input_returns_zero():
  + test_version_cmd_up_to_date(runner, monkeypatch):
  + test_version_cmd_update_available(runner, monkeypatch):
  + test_version_cmd_no_network(runner, monkeypatch):
  + test_upgrade_skips_when_already_up_to_date(runner, monkeypatch):
  + test_upgrade_skips_when_installed_is_newer(runner, monkeypatch):
  + test_upgrade_proceeds_when_update_available(runner, monkeypatch):
  + test_upgrade_proceeds_when_network_unavailable(runner, monkeypatch):
  + test_release_computes_patch_bump(runner, monkeypatch, tmp_path):
  + test_release_computes_minor_bump(runner, monkeypatch, tmp_path):
  + test_release_computes_major_bump(runner, monkeypatch, tmp_path):
  + test_release_aborts_on_n_at_commit(runner, monkeypatch, tmp_path):
  + test_release_stops_at_tag_if_n(runner, monkeypatch, tmp_path):
  + _setup_release_files(tmp_path: Path, version: str) -> None:

## tests/test_db.py
  + test_returns_sqlite_connection(tmp_path):
  + test_same_project_root_returns_same_connection(tmp_path):
  + test_db_file_created_at_expected_path(tmp_path):
  + test_wal_mode_enabled(tmp_path):
  + test_different_threads_get_different_connections(tmp_path):
  + test_db_filename_creates_named_db_file(tmp_path):
  + test_different_filenames_return_different_connections(tmp_path):
  + test_same_filename_same_thread_returns_cached_connection(tmp_path):
  + test_default_filename_is_memory_db(tmp_path):
  + test_different_project_roots_return_different_connections(tmp_path, tmp_path_factory):

## tests/test_embedder.py
  + _make_local_model(base: Path, folder_name: str) -> Path:
  + test_creates_hf_cache_structure(tmp_path):
  + test_no_op_when_snapshot_already_complete(tmp_path):
  + test_reseeds_when_snapshot_is_incomplete(tmp_path):
  + test_returns_false_when_local_model_folder_missing(tmp_path):
  + test_accepts_full_slug_folder_name(tmp_path):
  + test_idempotent_on_repeated_calls(tmp_path):
  + test_resolve_models_dir_uses_env_var(monkeypatch):
  + test_resolve_models_dir_autodetects_project_models(tmp_path, monkeypatch):
  + test_resolve_models_dir_returns_empty_when_no_models_folder(tmp_path, monkeypatch):

## tests/test_indexer.py
  + test_discover_files_finds_py_and_ts(tmp_project):
  + test_discover_files_excludes_gitignore(tmp_project):
  + test_full_index_creates_chunks(tmp_project):
  + test_full_index_writes_repo_map(tmp_project):
  + test_incremental_index_skips_unchanged(tmp_project):
  + test_incremental_index_processes_changed_file(tmp_project):
  + test_index_file_returns_chunk_count(tmp_project):
  + test_remove_file_clears_chunks(tmp_project):

## tests/test_lsp_client.py
  class _FakeStdout:
    + __init__(self, data: bytes) -> None:
    + read(self, n: int) -> bytes:
  class _FakeProc:
    + __init__(self, responses: list[bytes]) -> None:
    + terminate(self) -> None: ...
    + wait(self, timeout=None) -> None: ...
  + _frame(req_id: int, result: object) -> bytes:
  + test_request_returns_result():
  + test_open_file_sends_did_open_notification():
  + test_open_file_skips_duplicate():
  + test_request_timeout_raises():
  + test_notify_does_not_add_id():

## tests/test_lsp_filters.py
  + test_file_inside_project_is_included(tmp_path):
  + test_file_outside_project_is_excluded(tmp_path):
  + test_node_modules_excluded(tmp_path):
  + test_venv_excluded(tmp_path):
  + test_pycache_excluded(tmp_path):
  + test_nested_src_is_included(tmp_path):
  + test_venv_without_dot_excluded(tmp_path):

## tests/test_lsp_handlers.py
  + _make_router(client=None, *, raises=None):
  + _loc(path: str, line: int) -> dict:
  + test_find_definition_returns_location(tmp_path):
  + test_find_definition_filters_stdlib(tmp_path):
  + test_find_definition_null_result(tmp_path):
  + test_find_definition_unsupported_extension(tmp_path):
  + test_find_definition_server_unavailable(tmp_path):
  + test_find_references_returns_capped_list(tmp_path):
  + test_find_references_empty_result(tmp_path):
  + test_find_references_excludes_outside_project(tmp_path):
  + test_get_signature_splits_signature_and_docstring(tmp_path):
  + test_get_signature_null_result(tmp_path):
  + test_get_call_hierarchy_null_prepare(tmp_path):
  + test_get_call_hierarchy_returns_symbol(tmp_path):
  + test_warm_file_returns_ready(tmp_path):
  + test_warm_file_server_unavailable(tmp_path):

## tests/test_lsp_positions.py
  + test_offset_to_position_first_line():
  + test_offset_to_position_second_line():
  + test_offset_to_position_end_of_first_line():
  + test_position_to_offset_first_line():
  + test_position_to_offset_second_line():
  + test_roundtrip():
  + test_multibyte_emoji_counts_as_two_utf16_units():
  + test_position_past_end_of_line():

## tests/test_lsp_router.py
  + test_unsupported_extension_raises():
  + test_binary_not_found_raises():
  + test_get_client_creates_and_caches():
  + test_ts_extensions_share_one_client():
  + test_server_name_for_known_extensions():
  + test_server_name_for_unknown_extension():
  + test_shutdown_closes_all_clients():
  + test_custom_cmds_override_defaults():

## tests/test_mcp_lsp_tools.py
  + test_all_lsp_tool_names_present_in_source():
  + test_lsp_handler_imports_present_in_source():
  + test_handle_lsp_tool_returns_text_content():

## tests/test_mcp_memory_tools.py
  + test_memory_tool_names_present_in_source():
  + test_handle_store_memory_returns_id(tmp_path):
  + test_handle_recall_memory_returns_events(tmp_path):
  + test_handle_record_change_manifest_returns_count(tmp_path):
  + test_handle_get_change_manifest_returns_records(tmp_path):

## tests/test_memgram_mcp.py
  + test_db_path_removed():

## tests/test_memgram_store.py
  + test_save_returns_id(store):
  + test_save_increments_id(store):
  + test_save_rejects_unknown_type(store):
  + test_valid_observation_types_contains_expected():
  + test_created_at_is_unix_integer(store):
  + test_db_file_in_codebase_context_dir(tmp_path):
  + test_context_empty_on_fresh_db(store):
  + test_context_returns_saved_memories(store):
  + test_context_respects_limit(store):
  + test_context_result_has_required_fields(store):
  + test_search_finds_by_title(store):
  + test_search_finds_by_content(store):
  + test_search_with_type_filter(store):
  + test_search_empty_when_no_match(store):
  + test_session_end_saves_observation(store):

## tests/test_memory_store.py
  + test_store_can_be_instantiated(tmp_path):
  + test_store_event_returns_string_id(store):
  + test_store_event_ids_are_unique(store):
  + test_search_events_finds_by_content(store):
  + test_search_events_returns_required_fields(store):
  + test_search_events_filter_by_agent(store):
  + test_search_events_filter_by_event_type(store):
  + test_search_events_empty_when_no_match(store):
  + test_search_events_respects_limit(store):
  + test_create_and_get_task(store):
  + test_get_task_returns_none_for_unknown(store):
  + test_update_task_status(store):
  + test_list_tasks_returns_all(store):
  + test_list_tasks_filter_by_status(store):
  + test_task_has_required_fields(store):
  + test_record_manifest_returns_count(store):
  + test_get_manifest_returns_records(store):
  + test_get_manifest_empty_for_unknown_task(store):
  + test_get_manifest_scoped_to_task(store):
  + test_manifest_record_has_required_fields(store):
  + test_valid_event_types_constant_exists():
  + test_store_event_rejects_unknown_type(store):

## tests/test_migrate.py
  + test_parse_handoff_blocks_extracts_one_real_block():
  + test_parse_handoff_blocks_title_contains_agent_and_task():
  + test_parse_handoff_blocks_type_is_handoff():
  + test_parse_handoff_blocks_skips_template():
  + test_parse_handoff_blocks_content_contains_block_text():
  + test_parse_handoff_blocks_empty_on_no_blocks():
  + test_parse_decision_blocks_extracts_two_blocks():
  + test_parse_decision_blocks_titles():
  + test_parse_decision_blocks_type_is_decision():
  + test_parse_decision_blocks_content_contains_rationale():
  + test_parse_decision_blocks_returns_empty_when_no_decision_log():
  + test_run_migration_returns_correct_counts(tmp_path):
  + test_run_migration_archives_both_files(tmp_path):
  + test_run_migration_raises_if_already_migrated(tmp_path):
  + test_run_migration_does_not_raise_if_only_one_archive_exists(tmp_path):
  + test_run_migration_returns_zeros_when_nothing_to_migrate(tmp_path):
  + test_run_migration_handles_missing_decisions_file(tmp_path):
  + test_run_migration_handles_missing_handoff_file(tmp_path):
  + test_run_migration_records_saved_to_store(tmp_path):
  + test_cli_migrate_exits_0_and_prints_summary(tmp_path):
  + test_cli_migrate_exits_1_when_already_migrated(tmp_path):
  + test_cli_migrate_nothing_to_migrate(tmp_path):
  + test_cli_migrate_prints_both_counts(tmp_path):

## tests/test_parser.py
  + test_parse_python_class_and_methods():
  + test_parse_python_module_functions():
  + test_parse_python_method_has_parent():
  + test_parse_python_function_no_parent():
  + test_parse_python_signature_format():
  + test_parse_typescript_class():
  + test_parse_typescript_interface():
  + test_parse_typescript_type_alias():
  + test_parse_typescript_arrow_function():
  + test_parse_syntax_error_returns_empty_or_partial():
  + test_parse_c_free_functions():
  + test_parse_c_function_language():
  + test_parse_c_struct():
  + test_parse_cpp_free_functions():
  + test_parse_cpp_class_and_methods():
  + test_parse_cpp_method_has_parent():
  + test_unsupported_extension_raises():

## tests/test_repo_map.py
  + make_sym(name, sym_type, parent=None, sig="def foo()", filepath="src/utils.py", lang="python"):
  + test_repo_map_includes_file_header():
  + test_repo_map_function_has_plus_prefix():
  + test_repo_map_methods_indented_under_class():
  + test_repo_map_header_contains_stats():
  + test_repo_map_token_estimate_under_target():
  + test_files_sorted_by_depth_then_alpha():

## tests/test_retriever.py
  + test_search_returns_results(indexed_project):
  + test_search_results_have_required_fields(indexed_project):
  + test_search_language_filter(indexed_project):
  + test_search_filepath_filter(indexed_project):
  + test_get_symbol_exact_match(indexed_project):
  + test_get_symbol_returns_empty_for_unknown(indexed_project):
  + test_get_repo_map_returns_content(indexed_project):
  + test_get_repo_map_not_indexed_message(tmp_path):

## tests/test_utils.py
  + test_count_tokens_basic():
  + test_count_tokens_empty():
  + test_slugify_basic():
  + test_slugify_safe_for_chroma():
  + test_find_project_root_with_git(tmp_path):
  + test_find_project_root_no_git(tmp_path):
  + test_load_gitignore_parses(tmp_path):
  + test_is_ignored_gitignore(tmp_path):
  + test_is_ignored_always_ignore(tmp_path):

## codebase_context/lsp/client.py
  class LspClient:
    + __init__(self, cmd: list[str], root_uri: str) -> None:
    + open_file(self, path: str, source: str, language_id: str) -> None:
    + open_file_lazy(self, path: str) -> None:
    + request(self, method: str, params: dict, timeout: float = 5.0) -> Any:
    + notify(self, method: str, params: dict) -> None:
    + shutdown(self) -> None:
    + _next_id(self) -> int:
    + _send(self, msg: dict) -> None:
    + _reader(self) -> None:
    + _read_one_response(self) -> dict:
    + _initialize(self) -> None:

## codebase_context/lsp/filters.py
  + is_project_file(path: str, project_root: str) -> bool:

## codebase_context/lsp/handlers.py
  + _read_line(path: str, line: int) -> str:
  + _uri_to_path(uri: str) -> str:
  + _loc_to_ref(loc: dict, project_root: str) -> dict | None:
  + _get_client(router: LspRouter, file: str):
  + _error_for(exc: Exception) -> dict:
  + handle_find_definition(
  + handle_find_references(
  + handle_get_signature(
  + handle_get_call_hierarchy(
  + handle_warm_file(

## codebase_context/lsp/positions.py
  + _utf16_len(char: str) -> int:
  + offset_to_position(source: str, offset: int) -> dict[str, int]:
  + position_to_offset(source: str, line: int, character: int) -> int:

## codebase_context/lsp/router.py
  class UnsupportedExtensionError:
    + __init__(self, ext: str) -> None:
  class ServerUnavailableError:
    + __init__(self, lang: str, binary: str) -> None:
  class LspRouter:
    + __init__(
    + get_client(self, ext: str) -> LspClient:
    + server_name_for_ext(self, ext: str) -> str:
    + shutdown(self) -> None:

## codebase_context/memgram/mcp_server.py
  + _format_memories(memories: list[dict]) -> str:
  + _handle_mem_save(store, arguments: dict):
  + _handle_mem_context(store, arguments: dict):
  + _handle_mem_search(store, arguments: dict):
  + _handle_mem_session_end(store, arguments: dict):
  + run_server() -> None:
  + _run_server(server) -> None:

## codebase_context/memgram/store.py
  class MemgramStore:
    + __init__(self, project_root: str) -> None:
    + _conn(self):
    + save(self, title: str, content: str, type: str = "handoff") -> int:
    + context(self, limit: int = 10) -> list[dict]:
    + search(self, query: str, type: str | None = None, limit: int = 10) -> list[dict]:
    + session_end(self, summary: str) -> None:

## tests/fixtures/sample_c.c
  class UserService:
  + validate_email(const char *email) {
  + validate_password(const char *password) {

## tests/fixtures/sample_cpp.cpp
  class AuthService:
    + login(const std::string& email, const std::string& password) {
    + logout(const std::string& token) {
  + validate_email(const std::string& email) {
  + hash_password(const std::string& password) {

## tests/fixtures/sample_py.py
  class UserService:
    + create(self, email: str, password: str) -> "User":
    + find_by_email(self, email: str) -> "Optional[User]":
  + validate_email(email: str) -> str:
  + validate_password(password: str) -> bool:

## tests/fixtures/sample_ts.ts
  class AuthService:
    + login(email: string, password: string): Promise<User> {
  interface User
  type UserId
  + validateEmail(email: string): boolean {
  + hashPassword(password: string): string => {

## tests/fixtures/sample_project/src/api/auth.py
  class AuthRouter:
    + login(self, email: str, password: str) -> dict:
    + register(self, email: str, password: str) -> dict:
    + refresh(self, token: str) -> dict:

## tests/fixtures/sample_project/src/services/auth.ts
  class AuthService:
    + login(email: string, password: string): Promise<User> {
    + logout(userId: UserId): Promise<void> {

## tests/fixtures/sample_project/src/types/user.ts
  interface User
  type UserId

## tests/fixtures/sample_project/src/utils/validation.py
  + validate_email(email: str) -> str:
  + validate_password(password: str) -> bool:
