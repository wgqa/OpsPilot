"""Explicit historical S3 fixture selection; never used by production code.

Old regression scenarios cover tasks admitted before CONTUX. Preserve their
8/6 contract and every attempt/observation, rather than relaxing the new policy.
"""
from opspilot.domain.database import connect


def use_legacy_s3_budget_fixture(path, task_id):
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        assert connection.execute("SELECT COUNT(*) FROM d2_attempts WHERE task_id=? AND kind='MODEL'",(task_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM investigation_update_assessments WHERE task_id=?",(task_id,)).fetchone()[0] == 0
        connection.execute(
            """UPDATE task_execution_budgets SET policy_version='LEGACY_V1',
               model_limit=8,mcp_limit=6,aux_provider_limit=NULL WHERE task_id=?""",(task_id,),
        )
