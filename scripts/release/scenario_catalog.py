"""Versioned SPEC-002 inventory. Requirement membership is independent of evidence bindings."""
VERSION = 'spec-002-v1'
CASE = 'docs/product-stage/context/case/platform-requirements.md'
POLICY = 'TECHNICAL_SPEC.md'


def requirement(title, source_kind, reference, section, gate, scenarios):
    return dict(title=title, source_kind=source_kind, reference=reference, section=section,
                executable_required=gate, scenarios=scenarios)


REQUIREMENTS = {
    'REQ-001': requirement('Text-only E1 boundary', 'case_requirement', CASE, 'Функциональные ограничения', True, ['SCN-001']),
    'REQ-002': requirement('Explicit smartphone attributes', 'case_requirement', CASE, 'Данные и обязательные поля', True, ['SCN-002']),
    'REQ-003': requirement('Current kettle schema', 'team_policy', POLICY, '2. Область первой версии', True, ['SCN-003']),
    'REQ-004': requirement('Canonical quantities and units', 'case_requirement', CASE, 'Функциональные ограничения', True, ['SCN-004']),
    'REQ-005': requirement('No invented or foreign-object facts', 'case_requirement', CASE, 'Функциональные ограничения', True, ['SCN-005']),
    'REQ-006': requirement('Conflicts abstain without title priority', 'team_policy', POLICY, 'P04', True, ['SCN-006']),
    'REQ-007': requirement('Explicit model boundaries', 'team_policy', POLICY, 'P06–P07', True, ['SCN-007']),
    'REQ-008': requirement('Brand, adjacent subbrand and family', 'team_policy', POLICY, 'P05', True, ['SCN-008']),
    'REQ-009': requirement('Memory roles and ambiguous units', 'team_policy', POLICY, 'P08–P09', True, ['SCN-009']),
    'REQ-010': requirement('Versioned color aliases', 'team_policy', POLICY, 'P10–P11', True, ['SCN-010']),
    'REQ-011': requirement('Raw Unicode/HTML evidence', 'team_policy', POLICY, '0. Действующая политика команды', True, ['SCN-011']),
    'REQ-012': requirement('External batch and recoverable publication', 'team_policy', POLICY, '4. Выход', True, ['SCN-012']),
    'REQ-013': requirement('Provisional HTTP errors and recovery', 'team_policy', POLICY, 'P01', True, ['SCN-013']),
    'REQ-014': requirement('External runtime independent of packaged examples', 'team_policy', POLICY, 'P01–P02', True, ['SCN-014']),
    'REQ-015': requirement('Common candidate gate', 'team_policy', POLICY, 'FR-4. Проверка', True, ['SCN-015']),
    'REQ-016': requirement('Offline LLM response/failure/budget checks', 'team_policy', POLICY, 'FR-5. Маршрутизация', True, ['SCN-016']),
    'REQ-017': requirement('Packaged smoke is a separate reproducible path', 'team_policy', POLICY, '7. Метрики приёмки', True, ['SCN-017']),
    'REQ-101': requirement('Genuine seller attribute input', 'case_requirement', CASE, 'Функциональные ограничения', False, ['SCN-101']),
    'REQ-102': requirement('Laptop category attributes', 'case_requirement', CASE, 'Данные и обязательные поля', False, ['SCN-102']),
    'REQ-103': requirement('Real new-category and long-tail evaluation', 'case_requirement', CASE, 'Функциональные ограничения', False, ['SCN-103']),
    'REQ-104': requirement('Independent human category quality', 'case_requirement', CASE, 'Метрики успеха', False, ['SCN-104']),
    'REQ-105': requirement('Calibrated reliability threshold', 'case_requirement', CASE, 'Функциональные ограничения', False, ['SCN-105']),
    'REQ-106': requirement('Measured real model contribution and cost', 'case_requirement', CASE, 'Ожидаемый формат решения', False, ['SCN-106']),
    'REQ-107': requirement('Traffic and seller quality slices', 'case_requirement', CASE, 'Метрики успеха', False, ['SCN-107']),
    'REQ-108': requirement('Complete six-artifact final delivery', 'case_requirement', CASE, 'Артефакты сдачи', False, ['SCN-108']),
    'REQ-109': requirement('Operator review and feedback loop (case bonus)', 'case_requirement', CASE, 'Функциональные ограничения', False, ['SCN-109']),
    'REQ-110': requirement('Real data source preparation', 'team_policy', POLICY, 'FR-1. Предобработка', False, ['SCN-110']),
    'REQ-111': requirement('Final candidate on target VM', 'team_policy', POLICY, '8. Критерии MVP', False, ['SCN-111']),
    'REQ-201': requirement('Final organizer endpoints and transactions', 'unknown_condition', 'docs/REQUIREMENTS.md', 'Решения при отсутствии дополнительных разъяснений', False, ['SCN-201']),
}


def implemented(title, kind, cases=(), stages=(), suite=None):
    evidence = ([dict(kind='case', key=c) for c in cases]
                + [dict(kind='stage', key=s) for s in stages])
    for name in ([suite] if isinstance(suite, str) else suite or []):
        evidence.append(dict(kind='suite', key=name))
    return dict(title=title, kind=kind, state='implemented', evidence=evidence, issues=[])


def gap(title, state, issues, reason):
    return dict(title=title, kind='gap', state=state, evidence=[], issues=issues, reason=reason)


SCENARIOS = {
    'SCN-001': implemented('Reject target fields and nonempty seller data in current E1', 'negative',
                           ['qa-001/invalid_targets', 'generated/invalid-product']),
    'SCN-002': implemented('Phone title-only and labelled description, all seven fields', 'positive',
                           ['generated/phone-title-0', 'generated/description-761']),
    'SCN-003': implemented('Kettle title and description, all five fields', 'positive',
                           ['generated/kettle-title-0', 'generated/description-482', 'matrix/kettle-color']),
    'SCN-004': implemented('Millilitres/kilowatts canonicalize; kilograms do not become litres', 'boundary',
                           ['qa-001/capacity_conversion', 'generated/description-482', 'matrix/wrong-capacity-unit']),
    'SCN-005': implemented('Missing, negated, range, accessory and foreign facts are not filled', 'negative',
                           ['generated/missing', 'qa-001/negated_capacity', 'qa-001/power_range',
                            'qa-001/foreign_screen', 'qa-001/memory_card', 'qa-001/bundle_battery',
                            'matrix/auxiliary-power']),
    'SCN-006': implemented('Conflicting color and storage produce explicit abstention', 'negative',
                           ['generated/conflict', 'qa-001/memory_conflict']),
    'SCN-007': implemented('Explicit commercial name/5G retained; ambiguous slash code refused', 'boundary',
                           ['matrix/model-network', 'matrix/ambiguous-code', 'qa-001/inline_model']),
    'SCN-008': implemented('Adjacent Redmi wins; brand name is not body color', 'boundary',
                           ['matrix/subbrand', 'qa-001/brand_is_not_color']),
    'SCN-009': implemented('Roles/pair accepted; singleton, missing unit and G typo refused', 'boundary',
                           ['qa-001/memory_roles', 'qa-001/memory_pair', 'matrix/single-memory',
                            'matrix/missing-unit', 'matrix/typo-unit']),
    'SCN-010': implemented('Approved modifier keeps full quote; same color repeats agree', 'boundary',
                           ['matrix/marketing-color', 'qa-001/duplicate_color']),
    'SCN-011': implemented('HTML entities/emoji map to raw evidence; hidden facts rejected', 'boundary',
                           ['generated/html-phone', 'generated/html-kettle', 'qa-001/hidden_battery']),
    'SCN-012': implemented('Batch continues after invalid Product; malformed JSONL preserves prior pair', 'negative',
                           ['generated/after-invalid'], ['external_cli', 'prediction_manifest', 'malformed_jsonl_preserves_pair']),
    'SCN-013': implemented('400/413/415/422, safe 500 and HTTP recovery', 'negative',
                           ['generated/invalid-product'], ['http_invalid_json', 'http_wrong_media',
                            'http_body_limit', 'http_recovery_after_errors'], suite='api'),
    'SCN-014': implemented('Isolated CLI/socket parity for every oracle case; server cleaned up', 'boundary',
                           cases=['generated/unsupported', 'qa-001/unsupported'],
                           stages=['isolated_package_without_examples', 'server_cleanup', 'all_external_checks']),
    'SCN-015': implemented('Shared candidate gate and uncalibrated review-only configuration', 'negative',
                           suite=('verifier', 'config')),
    'SCN-016': implemented('Fake LLM proposals, failures, physical budgets and no secret leakage', 'negative',
                           suite=('llm', 'llm_bounds', 'llm_validation')),
    'SCN-017': implemented('Packaged six-card smoke plus checksum verification, explicitly synthetic', 'positive', suite='demo'),
    'SCN-101': gap('Seller input/evidence implementation', 'not_implemented', [36, 5], 'E1 rejects nonempty seller_attributes; source mapping and evidence migration are separate work.'),
    'SCN-102': gap('Laptop extraction', 'not_implemented', [124, 44], 'No accepted laptop schema/runtime in the default profile.'),
    'SCN-103': gap('Representative real new categories', 'not_verified', [124], 'Synthetic registry tests do not measure real category quality.'),
    'SCN-104': gap('Independent precision/recall/F1', 'not_verified', [6, 38], 'AI-assisted development and catalog silver are not independent human test.'),
    'SCN-105': gap('Calibrated threshold/auto-accept', 'not_implemented', [39], 'Heuristic review/abstain only; no arbitrary acceptance threshold.'),
    'SCN-106': gap('Real rules/model/hybrid comparison', 'not_verified', [125, 40, 25], 'Offline fake-provider success is not measured live quality or cost.'),
    'SCN-107': gap('Traffic/seller fairness evidence', 'not_verified', [53, 40], 'No approved representative weights/reference in this synthetic run.'),
    'SCN-108': gap('Full predictions/EDA/final slides and private delivery', 'not_verified', [8, 42], 'Smoke/export is not the six final artifacts or confirmed delivery.'),
    'SCN-109': gap('General operator acceptance/persistence workflow', 'not_implemented', [19, 50], 'Dictionary console and ranking do not implement general attribute review.'),
    'SCN-110': gap('Clean real-data preparation', 'not_verified', [5], 'No real data are opened or prepared by this runner.'),
    'SCN-111': gap('Target VM acceptance', 'not_verified', [82], 'Local socket and CI do not prove final deployed VM identity.'),
    'SCN-201': gap('Official HTTP transactions', 'unknown', [17], 'Organizers have not provided a final endpoint contract.'),
}

SUITES = {'verifier': 'tests/test_candidate_verifier.py', 'config': 'tests/test_config.py', 'llm': 'tests/test_llm.py',
          'llm_bounds': 'tests/test_llm_bounds.py', 'llm_validation': 'tests/test_llm_validation.py',
          'api': 'tests/test_api.py', 'demo': 'src/goodsai/demo.py'}

# A nonempty suite is insufficient if a required control has been removed.
# IDs match unittest discovery and are captured before TestSuite consumes its children.
EVIDENCE_TESTS = {
    'verifier': {
        'test_candidate_verifier.VerifierTests.' + name for name in (
            'test_malformed_candidates_have_fixed_safe_reasons',
            'test_number_requires_correct_evidence_unit_conversion_and_canonical_value',
            'test_same_candidate_gate_for_injected_rule_model_and_llm_sources',
            'test_instruction_and_example_spans_reject_rules_and_llm_but_keep_real_fact',
            'test_auxiliary_quantities_are_rejected_regardless_of_producing_method',
            'test_auxiliary_llm_quantity_stays_rejected_on_fresh_response_and_cache_replay',
            'test_positive_quantity_fallback_is_preserved_without_requiring_rule_discovery',
            'test_cli_manifest_and_api_expose_same_rejection_and_preserve_conflict',
        )},
    'config': {'test_config.ConfigTests.test_unsupported_policy_cannot_enable_llm_or_auto_accept'},
    # QA-002 acceptance must survive a green suite with a required test removed.
    'llm': {
        'test_llm.GroundingTests.test_grounded_values_get_exact_raw_evidence_and_stay_review',
        'test_llm.FailureTests.test_provider_failure_keeps_rule_output_and_adds_reason',
        'test_llm.FailureTests.test_budget_exhausted_and_circuit_breaker',
        'test_llm.ProviderTests.test_error_messages_never_contain_key_or_url',
        'test_llm.CacheTests.test_warm_hit_skips_provider_and_is_reverified',
        'test_llm.CliTests.test_llm_run_records_counts_without_text_or_secrets',
        'test_llm.PolicyTests.test_request_carries_only_visible_text_and_schema',
    },
    'llm_bounds': {
        'test_llm_bounds.LocalGateway.test_success_through_real_socket',
        'test_llm_bounds.LocalGateway.test_slow_gateway_is_cut_by_request_deadline',
        'test_llm_bounds.LocalGateway.test_daily_ledger_counts_physical_attempts_including_retries',
    },
    'llm_validation': {
        'test_llm_validation.ResponseValidationTests.test_malformed_top_level_non_json_and_duplicate_keys_fail_closed',
        'test_llm_validation.MalformedTransportTests.test_real_cli_batch_http_and_cache_replay_preserve_rules_and_continue',
    },
}
