from copy import deepcopy
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
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


class AuditLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.connections = []
        self.cursors = []
        self.fail_sql = None
        self.fail_cursor = False

    def connect(self, audit):
        # Keep strong references: neither CPython refcounting nor GC can hide a leak.
        owner = self

        class Cursor(sqlite3.Cursor):
            closed = False

            def execute(self, sql, *args):
                if owner.fail_sql and sql.startswith(owner.fail_sql):
                    raise sqlite3.OperationalError('Injected SQL failure')
                return super().execute(sql, *args)

            def close(self):
                self.closed = True
                return super().close()

        class Connection(sqlite3.Connection):
            closed = False

            def cursor(self):
                if owner.fail_cursor:
                    raise sqlite3.OperationalError('Injected cursor acquisition failure')
                cursor = super().cursor(factory=Cursor)
                owner.cursors.append(cursor)
                return cursor

            def close(self):
                self.closed = True
                return super().close()

        connection = sqlite3.connect(audit.path, timeout=10, factory=Connection)
        connection.execute('PRAGMA foreign_keys=ON').close()
        self.connections.append(connection)
        return connection

    def assert_closed(self):
        self.assertTrue(self.connections)
        for connection in self.connections:
            self.assertTrue(connection.closed)
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute('SELECT 1')
        for cursor in self.cursors:
            self.assertTrue(cursor.closed)

    @staticmethod
    def row():
        return rank([ReviewTask('synthetic', '761', 'brand', 1, ('conflicting_evidence',), True)],
                    RankPolicy(), now=10)['rows'][0]

    @staticmethod
    def count(path):
        with closing(sqlite3.connect(path)) as db, closing(db.cursor()) as cursor:
            return cursor.execute('SELECT COUNT(*) FROM actions').fetchone()[0]

    def test_every_public_operation_closes_retained_handles_and_allows_immediate_move_delete(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(QueueAudit, 'connect', lambda a: self.connect(a)):
            path = Path(folder) / 'audit.sqlite'
            audit = QueueAudit(path)

            def movable():
                self.assert_closed()
                moved = path.with_name('moved.sqlite')
                path.rename(moved)
                moved.rename(path)

            movable()
            action = audit.begin(self.row(), 'operator', now=10)
            movable()
            audit.finish(action, correct=True, now=70)
            movable()
            report = audit.report()
            self.assertEqual((report['completed'], report['operator_seconds'],
                              report['declared_correct_critical']), (1, 60, 1))
            self.assertFalse(report['independent_reference'])
            movable()
            path.unlink()
            self.assertFalse(path.exists())

    def test_duplicate_and_invalid_finish_preserve_prior_data_and_close_connections(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(QueueAudit, 'connect', lambda a: self.connect(a)):
            path = Path(folder) / 'audit.sqlite'
            audit = QueueAudit(path)
            action = audit.begin(self.row(), 'operator', now=10)
            with self.assertRaises(sqlite3.IntegrityError):
                audit.begin(self.row(), 'operator', now=11)
            audit.finish(action, correct=True, now=70)
            before = audit.report()
            with self.assertRaises(ValueError):
                audit.finish(action, correct=False, now=80)
            with self.assertRaises(ValueError):
                audit.finish(999, correct=True, now=80)
            self.assertEqual(audit.report(), before)
            self.assertEqual(self.count(path), 1)
            self.assert_closed()

    def test_body_exceptions_rollback_without_masking_exit_or_interrupt(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(QueueAudit, 'connect', lambda a: self.connect(a)):
            path = Path(folder) / 'audit.sqlite'
            audit = QueueAudit(path)
            for error in (RuntimeError, KeyboardInterrupt, SystemExit):
                with self.subTest(error=error), self.assertRaises(error):
                    with audit._transaction() as cursor:
                        cursor.execute("INSERT INTO actions(task_id) VALUES ('synthetic-rollback')")
                        raise error('Injected transaction failure')
                self.assertEqual(self.count(path), 0)
                self.assert_closed()

    def test_deferred_commit_failure_rolls_back_and_closes_resources(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(QueueAudit, 'connect', lambda a: self.connect(a)):
            path = Path(folder) / 'audit.sqlite'
            audit = QueueAudit(path)
            with closing(sqlite3.connect(path)) as db:
                db.executescript('''
                    CREATE TABLE parents (id INTEGER PRIMARY KEY);
                    CREATE TABLE children (parent_id INTEGER REFERENCES parents(id)
                        DEFERRABLE INITIALLY DEFERRED);
                    CREATE TRIGGER reject_commit AFTER INSERT ON actions BEGIN
                        INSERT INTO children VALUES (NEW.id);
                    END;
                ''').close()
            with self.assertRaises(sqlite3.IntegrityError):
                audit.begin(self.row(), 'operator', now=10)
            self.assertEqual(self.count(path), 0)
            self.assert_closed()

    def test_sql_failures_in_initialization_begin_finish_and_report_close_handles(self):
        for statement in ('CREATE TABLE', 'CREATE UNIQUE INDEX', 'INSERT INTO', 'UPDATE actions', 'SELECT'):
            with self.subTest(statement=statement), tempfile.TemporaryDirectory() as folder, \
                    patch.object(QueueAudit, 'connect', lambda a: self.connect(a)):
                path = Path(folder) / 'audit.sqlite'
                if statement.startswith('CREATE'):
                    self.fail_sql = statement
                    with self.assertRaises(sqlite3.OperationalError):
                        QueueAudit(path)
                else:
                    self.fail_sql = None
                    audit = QueueAudit(path)
                    action = audit.begin(self.row(), 'operator', now=10)
                    self.fail_sql = statement
                    with self.assertRaises(sqlite3.OperationalError):
                        if statement.startswith('INSERT'):
                            audit.begin(self.row() | {'task_id': 'other'}, 'operator', now=11)
                        elif statement.startswith('UPDATE'):
                            audit.finish(action, correct=True, now=70)
                        else:
                            audit.report()
                    self.fail_sql = None
                    self.assertEqual(self.count(path), 1)
                    self.assertEqual(audit.report()['completed'], 0)
                self.assert_closed()

    def test_cursor_acquisition_failure_still_closes_the_connection(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(QueueAudit, 'connect', lambda a: self.connect(a)):
            self.fail_cursor = True
            with self.assertRaises(sqlite3.OperationalError):
                QueueAudit(Path(folder) / 'audit.sqlite')
            self.assert_closed()


if __name__=='__main__':unittest.main()
