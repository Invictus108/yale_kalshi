import math
import re
import unittest
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch, Mock
from datetime import timedelta
from flask import g

from app import create_app
from app.extensions import db
from app.models import ChatMessage, DirectMessage, LedgerEntry, Market, Position, Trade, User, utcnow
from app.services.amm import trade_cost
from app.services.demo_seed import _seed_admin_balance_history
from app.services.friends import conversation, search_users, send_request
from app.services.ledger import apply_entry
from app.services.resolve import finalize_resolution, propose_resolution
from app.services.trading import execute_trade
from app.services.users import get_or_create_user
from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-only-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SEED_DEMO_DATA = False
    DEV_AUTH_BYPASS = True
    ENABLE_NETID_LOGIN = True
    FRIEND_ACCESS_CODE = ''
    BOOTSTRAP_ADMIN_NETID = 'testadmin'
    SMTP_HOST = ''
    SEED_BALANCE = 10000


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.admin = User.query.filter_by(netid='testadmin').one()
        self.user = get_or_create_user('student1')
        self.other = get_or_create_user('student2')
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def market(self, status='open', expired=False):
        market = Market(title='Will Yale win The Game?', description='Campus prediction.',
                        resolution_criteria='Official final score.', resolution_source='Yale Athletics',
                        creator_id=self.user.id, status=status, lmsr_b=100,
                        closes_at=utcnow() + timedelta(days=-1 if expired else 1))
        db.session.add(market)
        db.session.commit()
        return market

    def sign_in(self, admin=False):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id if admin else self.user.id)
            session['_fresh'] = True
            session['csrf_token'] = 'test-token'

    def post(self, path, **data):
        db.session.remove()
        g.pop('_login_user', None)
        return self.client.post(path, data={'csrf_token': 'test-token', **data})

    def test_invalid_trades_leave_balances_unchanged(self):
        market = self.market()
        for shares in [math.nan, math.inf, -math.inf, 0, -2, 1_000_001]:
            with self.subTest(shares=shares), self.assertRaises(ValueError):
                execute_trade(user_id=self.user.id, market=market, side='YES', action='BUY', shares=shares)
        self.assertEqual(self.user.ledger.balance, 10000)
        self.assertEqual(Position.query.count(), 0)
        for b in [0, -1, math.nan]:
            with self.assertRaises(ValueError):
                trade_cost(0, 0, b, 'YES', 'BUY', 1)
        with self.assertRaises(ValueError):
            apply_entry(self.user.id, math.nan, 'adjust')

    def test_buy_sell_round_trip_and_insufficient_funds(self):
        market = self.market()
        execute_trade(user_id=self.user.id, market=market, side='YES', action='BUY', shares=20)
        execute_trade(user_id=self.user.id, market=market, side='YES', action='SELL', shares=20)
        self.assertAlmostEqual(self.user.ledger.balance, 10000)
        self.assertAlmostEqual(market.q_yes, 0)
        with self.assertRaises(ValueError):
            execute_trade(user_id=self.user.id, market=market, side='NO', action='SELL', shares=1)
        with self.assertRaises(ValueError):
            execute_trade(user_id=self.user.id, market=market, side='YES', action='BUY', shares=100000)

    def test_settlement_state_and_dispute_window(self):
        market = self.market()
        execute_trade(user_id=self.user.id, market=market, side='YES', action='BUY', shares=20)
        with self.assertRaises(ValueError):
            finalize_resolution(market, admin_id=self.admin.id, outcome='YES')
        market.closes_at = utcnow() - timedelta(minutes=1)
        propose_resolution(market, proposer_id=self.user.id, outcome='YES', evidence='Official score')
        with self.assertRaises(ValueError):
            finalize_resolution(market, admin_id=self.admin.id, outcome='YES')
        market.dispute_deadline = utcnow() - timedelta(seconds=1)
        before = self.user.ledger.balance
        finalize_resolution(market, admin_id=self.admin.id, outcome='YES')
        self.assertAlmostEqual(self.user.ledger.balance, before + 20)
        with self.assertRaises(ValueError):
            finalize_resolution(market, admin_id=self.admin.id, outcome='YES')
        self.assertEqual(LedgerEntry.query.filter_by(kind='settle').count(), 1)

    def test_csrf_and_post_only_logout(self):
        self.sign_in()
        self.assertEqual(self.client.post('/settings', data={'display_name': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/settings', data={'csrf_token': '☃'}).status_code, 400)
        self.assertEqual(self.post('/settings', display_name='Good name').status_code, 302)
        self.assertEqual(User.query.filter_by(netid='student1').one().display_name, 'Good name')

    def test_safe_redirects_and_admin_preview_restriction(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            session['csrf_token'] = 'test-token'
        response = self.post('/login?next=https://evil.example', netid='student1')
        self.assertEqual(response.location, '/')
        self.post('/logout')
        self.app.config.update(DEV_AUTH_BYPASS=False, FRIEND_ACCESS_CODE='preview')
        with self.client.session_transaction() as session:
            session['csrf_token'] = 'test-token'
        response = self.post('/login', netid='testadmin', access_code='preview')
        self.assertEqual(response.location, '/login')
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)

    def test_admin_queue_and_reject_state(self):
        expired_id = self.market(expired=True).id
        pending_id = self.market(status='pending', expired=True).id
        self.sign_in(admin=True)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(Market, expired_id).status, 'closed')
        self.post(f'/admin/markets/{expired_id}/reject')
        self.assertEqual(db.session.get(Market, expired_id).status, 'closed')
        self.post(f'/admin/markets/{pending_id}/approve')
        self.assertEqual(db.session.get(Market, pending_id).status, 'pending')

    def test_latest_two_hundred_messages(self):
        market = self.market()
        for n in range(205):
            db.session.add(DirectMessage(sender_id=self.user.id, recipient_id=self.other.id, body=f'message-{n:03}'))
            db.session.add(ChatMessage(user_id=self.user.id, market_id=market.id, body=f'market-{n:03}'))
        db.session.commit()
        messages = conversation(self.user.id, self.other.id)
        self.assertEqual(len(messages), 200)
        self.assertEqual(messages[0].body, 'message-005')
        self.assertEqual(messages[-1].body, 'message-204')
        response = self.client.get(f'/markets/{market.id}')
        self.assertIn(b'market-204', response.data)
        self.assertNotIn(b'market-000', response.data)

    def test_anonymous_search_and_missing_friend(self):
        self.assertEqual(search_users('student1'), [])
        self.user.is_anonymous_display = False
        db.session.flush()
        self.assertIn(self.user, search_users('student1'))
        with self.assertRaises(ValueError):
            send_request(self.user.id, 999999)

    def test_demo_seed_preserves_real_ledger(self):
        apply_entry(self.admin.id, -25, 'trade', note='real trade')
        db.session.commit()
        before = [(e.id, e.amount, e.note) for e in self.admin.ledger.entries]
        balance = self.admin.ledger.balance
        _seed_admin_balance_history(self.admin.id)
        db.session.flush()
        self.assertEqual([(e.id, e.amount, e.note) for e in self.admin.ledger.entries], before)
        self.assertEqual(self.admin.ledger.balance, balance)

    def test_pages_render_and_forms_have_csrf(self):
        market = self.market()
        self.sign_in(admin=True)
        for path in ['/', '/portfolio', '/leaderboard', '/people', '/chat', '/settings', '/admin/', '/markets/new', f'/markets/{market.id}', f'/u/{self.user.id}']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertNotIn('Yale Markets', html)
                for form in re.findall(r'<form\b.*?</form>', html, re.S):
                    if 'method="post"' in form:
                        self.assertIn('name="csrf_token"', form)

    def test_malformed_dates_and_trade_requests(self):
        market_id = self.market().id
        self.sign_in()
        for value in ['nan', 'inf', '-inf', 'bad']:
            self.assertEqual(self.post(f'/markets/{market_id}/trade', shares=value).status_code, 302)
        response = self.post('/markets/new', closes_at='9999-12-31T23:59', tz_offset_minutes='840')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid close time', response.data)

    def test_email_header_failure_is_contained(self):
        from app.services.email_notify import send_email
        self.app.config['SMTP_HOST'] = 'unused.example'
        result, _ = send_email('test@example.com', 'Invalid\nSubject', 'Body')
        self.assertEqual(result, 'failed')

    def test_cas_response_with_and_without_prefix(self):
        from app.services.cas import validate_ticket
        for prefix in ['cas:', '']:
            xml = f'<{prefix}serviceResponse xmlns:cas="http://www.yale.edu/tp/cas"><{prefix}authenticationSuccess><{prefix}user>STUDENT1</{prefix}user></{prefix}authenticationSuccess></{prefix}serviceResponse>'
            with patch('app.services.cas.requests.get', return_value=Mock(text=xml)):
                self.assertEqual(validate_ticket('test-ticket'), 'student1')

    def test_concurrent_http_trades_cannot_double_spend(self):
        # A separate file DB gives each thread its own SQLite connection.
        with tempfile.TemporaryDirectory(prefix='yalshi-test-') as folder:
            class ConcurrentConfig(TestConfig):
                SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(Path(folder) / 'test.db')
            app = create_app(ConcurrentConfig)
            with app.app_context():
                user = User.query.filter_by(netid='testadmin').one()
                uid = user.id
                market = Market(title='Concurrent market', description='Test', resolution_criteria='Test',
                                resolution_source='Test', creator_id=uid, status='open', lmsr_b=100,
                                closes_at=utcnow()+timedelta(days=1))
                db.session.add(market)
                db.session.commit()
                mid = market.id
            barrier = Barrier(2)
            def buy(_):
                client = app.test_client()
                with client.session_transaction() as session:
                    session['_user_id'] = str(uid)
                    session['csrf_token'] = 'token'
                barrier.wait(timeout=10)
                return client.post(f'/markets/{mid}/trade', data={
                    'csrf_token': 'token', 'side': 'YES', 'action': 'BUY', 'shares': '9000'
                }).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(buy, range(2))), [302, 302])
            with app.app_context():
                self.assertEqual(Trade.query.count(), 1)
                self.assertEqual(Position.query.one().yes_shares, 9000)
                self.assertEqual(db.session.get(Market, mid).q_yes, 9000)
                self.assertGreaterEqual(db.session.get(User, uid).ledger.balance, 0)
                db.session.remove()
                db.engine.dispose()


if __name__ == '__main__':
    unittest.main()
