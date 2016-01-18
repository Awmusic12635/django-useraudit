from datetime import timedelta
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import mail
from django.core import management
from django.dispatch import receiver
from django.test import TestCase, override_settings
from django.utils import timezone
import re

from userlog_testapp.models import MyUser, MyProfile
import userlog.password_expiry


@override_settings(AUTH_USER_MODEL="userlog_testapp.MyUser")
class ExpiryTestCase(TestCase):
    username = "testuser"
    password = "testuser"

    def setUp(self):
        self.user = MyUser.objects.create(
            username=self.username,
            last_login=timezone.now(),
            password_change_date=timezone.now(),
            email="testuser@localhost",
        )
        self.user.set_password(self.password)
        self.user.save()

        type(self).password_expired_signal = None
        type(self).account_expired_signal = None

    def tearDown(self):
        self.user.delete()

    def authenticate(self):
        return authenticate(username=self.username, password=self.password)

    @property
    def user2(self):
        self.user.refresh_from_db()
        return self.user

    def setuser(self, **kwargs):
        for attr, val in kwargs.items():
            setattr(self.user, attr, val)
        self.user.save()

    ###########################################################################
    # account expiry test cases

    @override_settings(ACCOUNT_EXPIRY_DAYS=5)
    def test_not_expired(self):
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)

    @override_settings(ACCOUNT_EXPIRY_DAYS=5)
    def test_expired(self):
        self.setuser(last_login=timezone.now() - timedelta(days=6))
        u = self.authenticate()
        self.assertIsNone(u)
        self.assertFalse(self.user2.is_active)

    @override_settings(ACCOUNT_EXPIRY_DAYS=-5)
    def test_expiry_disabled(self):
        self.setuser(last_login=timezone.now() - timedelta(days=10000))
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)

    @override_settings(ACCOUNT_EXPIRY_DAYS=5)
    def test_fresh_user(self):
        self.setuser(last_login=None)
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)


    ###########################################################################
    # password expiry test cases

    def test_changing_of_password_updates_password_change_date_field(self):
        self.setuser(password_change_date=timezone.now() - timedelta(days=1))
        before_the_change = timezone.now()
        self.user.set_password('the new password')
        self.user.save()
        self.user.refresh_from_db()
        self.assertGreater(self.user.password_change_date, before_the_change)

    def test_saving_same_password_does_not_update_password_change_date_field(self):
        one_day_ago = password_change_date=timezone.now() - timedelta(days=1)
        self.setuser(password_change_date=one_day_ago)
        self.user.set_password('testuser') # same password
        self.user.save()
        self.user.refresh_from_db()
        self.assertEquals(one_day_ago, self.user.password_change_date, "Password change date shouldn't change")


    @override_settings(PASSWORD_EXPIRY_DAYS=5)
    def test_password_not_expired(self):
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)

    @override_settings(PASSWORD_EXPIRY_DAYS=5)
    def test_password_expired(self):
        self.setuser(password_change_date=timezone.now() - timedelta(days=6))
        u = self.authenticate()
        self.assertIsNone(u)
        self.assertTrue(self.user2.is_active)

    @override_settings(PASSWORD_EXPIRY_DAYS=-5)
    def test_password_expiry_disabled(self):
        self.setuser(password_change_date=timezone.now() - timedelta(days=10000))
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)

    @override_settings(PASSWORD_EXPIRY_DAYS=5)
    def test_fresh_user_password(self):
        self.setuser(password_change_date=None)
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)

    @override_settings(PASSWORD_EXPIRY_DAYS=5)
    def test_password_expired_signal(self):
        self.setuser(password_change_date=timezone.now() - timedelta(days=6))
        self.authenticate()
        self.assertIsNotNone(self.password_expired_signal)
        self.assertEquals(self.password_expired_signal["sender"], type(self.user))
        self.assertEquals(self.password_expired_signal["user"], self.user)

    ###########################################################################
    # account expiry notification test cases

    @override_settings(ACCOUNT_EXPIRY_DAYS=5)
    def test_command_notification(self):
        self.setuser(last_login=timezone.now() - timedelta(days=6))
        management.call_command("disable_inactive_users", verbosity=0, email=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(re.search(r"expired", mail.outbox[0].subject, re.I))

    ###########################################################################
    # inactive account test cases

    def test_user_is_active(self):
        self.setuser(is_active=False)
        user = self.authenticate()
        self.assertIsNone(user)


@receiver(userlog.password_expiry.password_has_expired)
def handle_password_expired(**kwargs):
    ExpiryTestCase.password_expired_signal = kwargs


@receiver(userlog.password_expiry.account_has_expired)
def handle_account_expired(**kwargs):
    ExpiryTestCase.account_expired_signal = kwargs


@override_settings(
    AUTH_USER_MODEL="auth.User",
    AUTH_USER_MODEL_PASSWORD_CHANGE_DATE_ATTR="myprofile.password_change_date",
)
class ProfileExpiryTestCase(TestCase):
    username = "testuser"
    password = "testuser"

    def setUp(self):
        self.user = User.objects.create(
            username=self.username,
            last_login=timezone.now(),
            email="testuser@localhost",
        )
        self.user.set_password(self.password)
        self.user.save()
        MyProfile.objects.create(
            user=self.user,
            password_change_date=timezone.now(),
        )

    def tearDown(self):
        self.user.delete()

    def authenticate(self):
        return authenticate(username=self.username, password=self.password)

    @property
    def user2(self):
        self.user.refresh_from_db()
        return self.user

    ###########################################################################
    # user profile password expiry test cases

    def test_changing_of_password_updates_password_change_date_field(self):
        self.user.myprofile.password_change_date = timezone.now() - timedelta(days=1)
        self.user.myprofile.save()
        before_the_change = timezone.now()
        self.user.set_password('the new password')
        self.user.save()
        self.user.refresh_from_db()
        self.assertGreater(self.user.myprofile.password_change_date, before_the_change)

    @override_settings(PASSWORD_EXPIRY_DAYS=5)
    def test_password_not_expired(self):
        u = self.authenticate()
        self.assertIsNotNone(u)
        self.assertTrue(u.is_active)

    @override_settings(PASSWORD_EXPIRY_DAYS=5)
    def test_password_expired(self):
        self.user.myprofile.password_change_date = timezone.now() - timedelta(days=6)
        self.user.myprofile.save()
        u = self.authenticate()
        self.assertIsNone(u)
        self.assertTrue(self.user2.is_active)

    @override_settings(
        AUTH_USER_MODEL_PASSWORD_CHANGE_DATE_ATTR="myprofile.asdfgh",
    )
    def test_password_expired_bad_attr(self):
        u = self.authenticate()
        # fixme: need to check for log warning
        self.assertIsNotNone(u)

    @override_settings(
        PASSWORD_EXPIRY_DAYS=5,
        AUTH_USER_MODEL_PASSWORD_CHANGE_DATE_ATTR="myprofile.user.myprofile.user.myprofile.password_change_date",
    )
    def test_password_expired_attr(self):
        self.user.myprofile.password_change_date = timezone.now() - timedelta(days=6)
        self.user.myprofile.save()
        u = self.authenticate()
        self.assertIsNone(u)
        self.assertTrue(self.user2.is_active)
