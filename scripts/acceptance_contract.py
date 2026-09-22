"""Required automated backend subassertions. UI/manual/model gates stay separate."""

REQUIRED = {
    "AC-02": [
        "test_missing_real_configuration_explicit",
        "test_real_configuration_error_never_prints_supplied_key",
        "test_disabled_mqtt_health_explicit",
    ],
    "AC-03": [
        "test_three_clients_60_seconds_and_control",
        "test_mqtt_to_database_reject_then_accept",
    ],
    "AC-04": ["test_three_clients_60_seconds_and_control", "test_four_service_dependency_recovery"],
    "AC-05": [
        "test_retransmit_different_received_time",
        "test_mqtt_to_database_reject_then_accept",
    ],
    "AC-06": ["test_conflict_never_overwrites"],
    "AC-07": ["test_old_and_equal_timestamps_preserve_snapshot"],
    "AC-08": [
        "test_valid_json_strings_parse",
        "test_strict_finite_numbers",
        "test_invalid_fields",
        "test_time_boundaries",
        "test_real_retained_invalid_inputs_then_valid_sample",
    ],
    "AC-09": ["test_freshness_boundaries", "test_old_but_fresh_on_arrival_cannot_extend_live_time"],
    "AC-10": ["test_restart_and_replay", "test_four_service_dependency_recovery"],
    "AC-11": [
        "test_real_api_scenarios_and_offline_recovery",
        "test_three_clients_60_seconds_and_control",
    ],
    "AC-12": ["test_real_api_scenarios_and_offline_recovery"],
    "AC-13": [
        "test_timeout_uses_monotonic_and_late_ack",
        "test_mismatched_ack_and_broker_unavailable",
        "test_default_five_second_ack_deadline",
        "test_expired_command_does_not_remain_pending_after_db_busy",
    ],
    "AC-14": ["test_devices_empty_and_unknown", "test_empty_values_are_null"],
    "AC-15": [
        "test_bad_history_window",
        "test_history_and_statistics_full_window",
        "test_history_5001_rows_rejected",
    ],
    "AC-16": ["test_reservation_idempotency_precedes_slot", "test_http_concurrency_and_retries"],
    "AC-17": ["test_reservation_idempotency_precedes_slot", "test_http_concurrency_and_retries"],
    "AC-18": [
        "test_20_concurrent_independent_transactions",
        "test_historical_hot_sample_and_index",
    ],
    "AC-19": [
        "test_authorization_denied",
        "test_rejected_registered_write_has_server_trace",
        "test_real_adapter_preserves_assistant_tool_calls_and_pairing",
    ],
    "AC-20": [
        "test_invalid_evidence",
        "test_evidence_must_belong_to_current_run",
        "test_offline_evidence_is_rechecked_after_recovery",
        "test_historical_hot_sample_and_index",
        "test_schema_cannot_accept_server_context",
        "test_reused_order_retains_this_calls_selected_evidence",
    ],
    "AC-21": [
        "test_five_serial_model_requests_use_real_tools",
        "test_valid_batched_reads_and_cumulative_tool_budget",
        "test_protocol_validation",
        "test_duplicate_ids_and_model_budget",
    ],
    "AC-22": ["test_get_fault_guide_versions_and_unknown_code"],
    "AC-23": [
        "test_invalid_protocol_and_arguments",
        "test_entire_batch_is_validated_before_side_effects",
    ],
    "AC-24": [
        "test_default_model_and_tool_timeouts",
        "test_real_http_errors_without_retry",
        "test_sqlite_busy_timeout_is_explicit_and_bounded",
    ],
    "AC-25": ["test_tool_output_injection_cannot_add_write_permission"],
    "AC-26": [
        "test_tool_budget",
        "test_duplicate_ids_and_model_budget",
        "test_valid_batched_reads_and_cumulative_tool_budget",
        "test_http_concurrency_and_retries",
    ],
    "AC-27": [
        "test_default_total_90_seconds_with_frozen_data_clock",
        "test_restart_interrupts_pending_runs_preserves_order_and_history",
        "test_deadline_covers_response_persistence",
    ],
    "AC-28": [
        "test_result_and_order_roll_back_together",
        "test_commit_boundary_before_and_after",
        "test_old_order_is_not_proof_of_current_write",
        "test_db_unavailable_during_write_recovery_returns_unknown",
    ],
}
