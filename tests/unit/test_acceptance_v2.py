from pathlib import Path

from scripts.acceptance_v2 import junit_assertions, status_code
from scripts.acceptance_v2_contract import ASSERTIONS, GROUPS, SUITES


def test_status_precedence_and_missing_tests_are_not_success(tmp_path):
    assert status_code(["PASS", "PENDING_REVIEW", "FAIL", "BLOCKED"]) == 2
    assert status_code(["PENDING_REVIEW", "FAIL"]) == 1
    assert status_code(["NOT_RUN"]) == 1
    assert status_code(["PENDING_REVIEW"]) == 3
    assert status_code(["PASS"]) == 0
    report = junit_assertions(tmp_path / "absent.xml", [4])["XAC-04"]
    assert report["status"] == "NOT_RUN"
    assert report["automatic_subassertions"]["status"] == "NOT_RUN"


def test_junit_subassertion_cannot_certify_whole_xac(tmp_path):
    name = ASSERTIONS[4][1][0]
    path = tmp_path / "result.xml"
    path.write_text(
        f'<testsuites><testsuite><testcase name="{name}" time="1.2"/></testsuite></testsuites>'
    )
    report = junit_assertions(path, [4])["XAC-04"]
    # Additional named endpoint checks can remain NOT_RUN, never infer whole-XAC success.
    assert report["status"] == "NOT_RUN"
    assert report["automatic_subassertions"]["tests"][0]["status"] == "PASS"
    path.write_text(
        f'<testsuites><testsuite><testcase name="{name}"><skipped/></testcase></testsuite></testsuites>'
    )
    assert junit_assertions(path, [4])["XAC-04"]["automatic_subassertions"]["status"] == "NOT_RUN"


def test_all_declared_tests_exist_in_selected_suite_sources():
    for suite in SUITES.values():
        content = "\n".join(
            Path(path).read_text() for group in suite["groups"] for path in GROUPS[group]
        )
        for identifier in suite["ids"]:
            for name in ASSERTIONS[identifier][1]:
                assert f"def {name}(" in content, (identifier, name)
