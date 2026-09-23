"""Named automatic subassertions; none of these mappings alone certify a whole XAC."""

GROUPS = {
    "migration": ("tests/integration/test_migrations.py",),
    "protocol": (
        "tests/unit/test_telemetry_v2.py",
        "tests/integration/test_session_reporting.py",
        "tests/unit/test_report_delivery.py",
        "tests/integration/test_mqtt_ingestion.py",
        "tests/unit/test_simulator_charging.py",
    ),
    "control": (
        "tests/integration/test_charging_commands.py",
        "tests/integration/test_charging_sessions.py",
        "tests/integration/test_simulator_operations_stack.py",
    ),
    "power": ("tests/unit/test_power_allocation.py", "tests/integration/test_power_plans.py"),
    "alarm": ("tests/unit/test_alarm_rules.py", "tests/integration/test_alarms.py"),
    "orders": (
        "tests/integration/test_work_order_lifecycle.py",
        "tests/integration/test_work_orders.py",
        "tests/integration/test_operations.py",
        "tests/integration/test_v2_write_idempotency.py",
    ),
    "timeline": (
        "tests/integration/test_timeline_v2.py",
        "tests/integration/test_timeline_sources.py",
        "tests/integration/test_simulator_scripts.py",
        "tests/integration/test_simulator_script_boundaries.py",
    ),
    "knowledge": (
        "tests/unit/test_knowledge_index.py",
        "tests/integration/test_knowledge_search.py",
        "tests/unit/test_answer_refs.py",
        "tests/integration/test_agent_references.py",
    ),
    "agent": (
        "tests/unit/test_agent_v2_schemas.py",
        "tests/integration/test_agent_workflow.py",
        "tests/integration/test_run_idempotency.py",
        "tests/integration/test_fleet_queries.py",
        "tests/integration/test_patrols.py",
        "tests/integration/test_eval_v2_runner.py",
    ),
    "recovery": (
        "tests/integration/test_recovery.py",
        "tests/integration/test_mqtt_ingestion.py",
        "tests/integration/test_runtime_monitor.py",
    ),
}

# Each label identifies precisely the part supported by the named tests.
ASSERTIONS = {
    1: (
        "旧行/摘要、空库迁移与ORM一致",
        [
            "test_upgrade_preserves_v1_business_rows",
            "test_legacy_evidence_digest_unchanged",
            "test_schema_matches_orm",
            "test_empty_database_has_versioned_schema",
        ],
    ),
    2: (
        "迁移摘要拒绝与DDL原子回滚",
        [
            "test_migration_checksum_tampering_rejected",
            "test_failed_migration_rolls_back_ddl_and_version",
        ],
    ),
    3: (
        "WAL备份及拒绝覆盖恢复",
        [
            "test_backup_includes_wal_and_restore_refuses_overwrite",
            "test_migration_cli_offline_backup_restore",
        ],
    ),
    4: (
        "共享操作幂等/冲突/回滚及各新写路由重复5次",
        [
            "test_operation_idempotency_conflict_and_rollback",
            "test_all_new_write_routes_repeat_five_and_reject_changed_content",
        ],
    ),
    5: ("合法v1/v2 JSON", ["test_dual_json_versions"]),
    6: (
        "每个v2数字字段严格类型及真实Broker拒绝后恢复",
        [
            "test_v2_rejects_invalid_fields",
            "test_v2_cross_field_consistency",
            "test_each_v2_numeric_field_is_strict_and_nonnegative",
            "test_real_retained_invalid_inputs_then_valid_sample",
        ],
    ),
    7: (
        "接收服务重复/冲突/retained不刷新",
        ["test_v2_ingestion_duplicates_conflicts_and_retained_do_not_refresh"],
    ),
    8: (
        "实际报告入库/ACK/冲突/在线独立",
        ["test_real_broker_report_commit_ack_duplicate_conflict_and_no_live_refresh"],
    ),
    9: (
        "报告退避/过期/积压",
        [
            "test_retry_schedule_ack_matching_and_expired_evidence",
            "test_pending_reports_bounded_and_backlog_refuses_start_but_allows_stop",
        ],
    ),
    10: (
        "报告与控制不刷新在线",
        ["test_real_broker_report_commit_ack_duplicate_conflict_and_no_live_refresh"],
    ),
    11: ("实际HTTP与MQTT启停反馈", ["test_http_start_stop_idempotency_and_verified_feedback"]),
    12: (
        "真实控制报告与generation围栏",
        [
            "test_operations_simulator_real_mqtt_control_and_reports",
            "test_rejected_high_generation_fences_later_lower_command",
            "test_ten_duplicate_controls_conflict_old_generation_and_expiry",
        ],
    ),
    13: (
        "同设备并发与参数拒绝",
        ["test_concurrent_start_serializes_per_device_and_rejects_invalid_inputs"],
    ),
    14: (
        "默认ACK超时、晚回执、幂等恢复",
        ["test_no_ack_times_out_and_duplicate_request_reuses_original"],
    ),
    15: ("4秒验证deadline", ["test_slow_effect_query_cannot_verify_after_four_second_deadline"]),
    16: (
        "提交发布窗口与重启不重放",
        ["test_commit_before_publish_restart_preserves_request_without_replay"],
    ),
    17: (
        "分段整数积分与真实模拟器",
        [
            "test_energy_integrates_fractional_wh_without_sample_rounding",
            "test_operations_simulator_real_mqtt_control_and_reports",
        ],
    ),
    18: (
        "报告原始事实与终态约束",
        ["test_real_broker_report_commit_ack_duplicate_conflict_and_no_live_refresh"],
    ),
    19: ("遥测静默和报告分离", ["test_operations_simulator_real_mqtt_control_and_reports"]),
    20: (
        "真实进程及容器SIGKILL保表底",
        [
            "test_simulator_process_kill_preserves_published_meter",
            "test_owned_four_service_operations_volume_survives_kill",
        ],
    ),
    21: ("会话窗口统计", ["test_sessions_full_window_statistics_and_stable_pagination"]),
    22: ("稳定分页与完整统计", ["test_sessions_full_window_statistics_and_stable_pagination"]),
    23: ("equal及100W确定余量", ["test_equal_water_filling_and_stable_100w_remainder"]),
    24: (
        "priority/零预算/非法输入",
        ["test_priority_caps_and_zero_budget", "test_reject_invalid_power_inputs"],
    ),
    25: ("预览控制指纹及120秒失效", ["test_preview_control_fingerprint_and_expiry"]),
    26: (
        "三设备实际先降后升",
        ["test_real_three_device_plan_preview_and_decrease_before_increase"],
    ),
    27: (
        "失败停止和真实30秒deadline",
        [
            "test_real_three_device_plan_preview_and_decrease_before_increase",
            "test_plan_uses_real_thirty_second_deadline_and_clears_slot",
        ],
    ),
    28: (
        "计划槽位与执行指纹",
        [
            "test_preview_control_fingerprint_and_expiry",
            "test_plan_uses_real_thirty_second_deadline_and_clears_slot",
        ],
    ),
    29: ("告警确认/新鲜恢复基础", ["test_alarm_ack_is_not_recovery_stale_unknown_and_fresh_clear"]),
    30: (
        "连续独立观测与持久化触发",
        [
            "test_only_continuous_unique_samples_advance_duration",
            "test_persisted_trigger_duration_resets_after_out_of_order_sample",
        ],
    ),
    31: ("新鲜连续恢复与stale", ["test_alarm_ack_is_not_recovery_stale_unknown_and_fresh_clear"]),
    32: ("确认不等于恢复与版本", ["test_alarm_ack_is_not_recovery_stale_unknown_and_fresh_clear"]),
    33: (
        "变更禁用规则保留旧版本",
        ["test_changed_disabled_rule_preserves_active_rule_and_restart_unknown"],
    ),
    34: (
        "重启unknown后恢复",
        ["test_changed_disabled_rule_preserves_active_rule_and_restart_unknown"],
    ),
    35: (
        "生命周期、说明与恢复合同",
        ["test_work_order_transitions_require_current_recovery_and_cleared_alarm"],
    ),
    36: (
        "IN_PROGRESS/RESOLVED各20独立事务",
        ["test_twenty_independent_creates_reuse_in_progress_and_resolved"],
    ),
    37: (
        "关单需新鲜且关联告警已恢复",
        ["test_work_order_transitions_require_current_recovery_and_cleared_alarm"],
    ),
    38: (
        "迁移事务回滚不留事件/请求",
        ["test_transition_rollback_keeps_status_event_and_request_atomic"],
    ),
    39: (
        "元数据/块边界/目录拒绝/旧版过滤",
        [
            "test_corpus_metadata_and_deterministic_bounded_chunks",
            "test_rejects_external_symlink_before_reading",
            "test_rebuild_failure_retains_old_version_and_wrong_model_is_filtered",
        ],
    ),
    40: (
        "FTS语法与有界检索",
        [
            "test_cold_start_indexes_sources_and_serves_safe_bounded_search",
            "test_body_only_incidental_word_does_not_answer_unrelated_subject",
        ],
    ),
    41: (
        "原子重建/FTS缺失/自动导入",
        [
            "test_rebuild_failure_retains_old_version_and_wrong_model_is_filtered",
            "test_missing_fts_module_exposes_failed_health_without_partial_schema",
            "test_cold_start_indexes_sources_and_serves_safe_bounded_search",
        ],
    ),
    43: (
        "API拒绝跨run引用；网页与真实注入另验",
        ["test_real_search_refs_persist_and_previous_run_evidence_is_rejected"],
    ),
    44: (
        "原协议预算和批校验",
        [
            "test_exact_nine_tools_and_single_write_tool",
            "test_new_read_tools_reject_server_context_and_are_exposed_without_write_permission",
            "test_entire_batch_is_validated_before_side_effects",
            "test_default_model_and_tool_timeouts",
            "test_default_total_90_seconds_with_frozen_data_clock",
            "test_tool_budget",
        ],
    ),
    45: (
        "完整fleet/空数据与报告",
        [
            "test_fleet_keeps_empty_devices_and_aggregates_more_than_display_limit",
            "test_default_fixture_patrol_and_invalid_first_tool",
        ],
    ),
    46: (
        "槽位竞争、幂等及忙碌跳过",
        [
            "test_chat_patrol_race_and_shutdown_preserve_partial_snapshot",
            "test_periodic_busy_skip_unique_due_disable_and_restart_no_catchup",
        ],
    ),
    47: (
        "周期唯一、禁用/重启不补跑",
        ["test_periodic_busy_skip_unique_due_disable_and_restart_no_catchup"],
    ),
    48: (
        "失败/关闭/恢复部分事实",
        [
            "test_manual_patrol_idempotency_single_slot_and_failure_facts",
            "test_restart_recovers_committed_tool_before_report_save",
        ],
    ),
    49: (
        "混合来源、稳定游标及只读",
        [
            "test_all_event_sources_link_exact_records_and_keep_late_receipts",
            "test_http_timeline_cursor_preserves_full_counts_and_scope",
        ],
    ),
    50: (
        "两个60秒真实脚本及取消边界",
        [
            "test_two_fixed_sixty_second_scripts_real_broker",
            "test_cancel_manual_override_missing_ack_and_restart_stop_remaining_steps",
        ],
    ),
    54: (
        "原四服务依赖恢复；v2完整冷启动另验",
        [
            "test_four_service_dependency_recovery",
            "test_owned_four_service_operations_volume_survives_kill",
        ],
    ),
    57: (
        "关闭恢复、任务计数与正常应用隔离",
        [
            "test_restart_interrupts_pending_runs_preserves_order_and_history",
            "test_runtime_counts_real_guardians_and_normal_app_has_no_test_route",
        ],
    ),
}

SUITES = {
    "iot": {
        "groups": ["migration", "protocol", "control", "power", "alarm", "orders", "timeline"],
        "ids": list(range(1, 39)) + [49, 50],
    },
    "ai": {"groups": ["knowledge", "agent"], "ids": [39, 40, 41, 43, 44, 45, 46, 47, 48]},
    "resilience": {
        "groups": ["migration", "protocol", "control", "power", "timeline", "recovery"],
        "ids": [2, 3, 9, 16, 20, 27, 28, 34, 48, 50, 54, 57],
    },
}
# Add stateful alarm/patrol modules for resilience assertions 34/48.
SUITES["resilience"]["groups"] += ["alarm", "agent"]
