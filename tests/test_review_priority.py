from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from goodsai.review_priority import ReviewTask,RankPolicy,rank,QueueAudit
from goodsai.contracts import Product


class ReviewPriorityTests(unittest.TestCase):
    def tasks(self):
        return [ReviewTask(f'critical-{i}','761','brand',900,('conflicting_evidence',)) for i in range(20)]+[
            ReviewTask('old-rare','482','color',1,(),False,'review'),
            ReviewTask('mandatory','761','ram_gb',900,(),True,'abstain')]

    def test_determinism_explanation_and_reserved_service(self):
        tasks=self.tasks();original=deepcopy(tasks);policy=RankPolicy()
        first=rank(tasks,policy,now=1000)
        self.assertEqual(first,rank(reversed(tasks),policy,now=1000))
        self.assertEqual(tasks,original)
        self.assertTrue(first['rows'][0]['task_id'].startswith('critical'))
        self.assertLess(next(r['rank'] for r in first['rows'] if r['task_id']=='old-rare'),11)
        self.assertEqual(first['rows'][7]['priority']['selected_by'],'oldest_quota')
        self.assertTrue(all(r['priority']['demand_weight']==1 and r['policy_sha256'] for r in first['rows']))

    def test_cursor_preserves_fairness_across_single_item_batches(self):
        remaining=self.tasks();cursor=0;served=[]
        for _ in range(10):
            report=rank(remaining,RankPolicy(),now=1000,cursor=cursor,limit=1)
            row=report['rows'][0];served.append(row['task_id']);cursor=report['next_cursor']
            remaining=[t for t in remaining if t.task_id!=row['task_id']]
        self.assertIn('old-rare',served)

    def test_demand_requires_approval_is_bounded_and_does_not_change_decisions(self):
        tasks=self.tasks();profile={'approval':'schema-owner-dev-v1','weights':{'761:brand':2}}
        with self.assertRaises(ValueError):rank(tasks,RankPolicy(),now=1000,demand=profile)
        policy=RankPolicy(demand_approval='schema-owner-dev-v1')
        ranked=rank(tasks,policy,now=1000,demand=profile)
        self.assertTrue(all(r['decision'] in {'review','abstain'} for r in ranked['rows']))
        with self.assertRaises(ValueError):rank(tasks,policy,now=1000,demand=profile|{'weights':{'761:brand':999}})
        with self.assertRaises(ValueError):Product.from_dict({'schema_version':'0.1','sku_id':'x','title':'test','clicks':1})

    def test_audit_sessions_are_immutable_and_quality_is_declared_not_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            audit=QueueAudit(Path(folder)/'audit.sqlite')
            row=rank(self.tasks(),RankPolicy(),now=1000)['rows'][0]
            action=audit.begin(row,'operator',now=1000);audit.finish(action,correct=True,now=1060)
            report=audit.report()
            self.assertEqual((report['operator_seconds'],report['declared_correct_critical']),(60,1))
            self.assertFalse(report['independent_reference']);self.assertIsNone(report['sales_impact'])
            with self.assertRaises(ValueError):audit.finish(action,correct=False,now=1070)

    def test_invalid_inputs_cannot_distort_queue(self):
        with self.assertRaises(ValueError):rank(self.tasks()*2,RankPolicy(),now=1000)
        with self.assertRaises(ValueError):rank(self.tasks(),RankPolicy(),now=1)
        with self.assertRaises(ValueError):RankPolicy(max_demand_weight=float('nan'))
        with self.assertRaises(ValueError):ReviewTask('x','761','brand',float('inf'),())


if __name__=='__main__':unittest.main()
