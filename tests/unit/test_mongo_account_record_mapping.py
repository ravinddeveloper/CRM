from datetime import datetime, timezone

from apps.accounts.repositories.mongo import MongoAccountRepository


def test_mongo_account_document_maps_security_profile_and_tokens():
    naive_time = datetime(2026, 1, 2, 3, 4, 5)
    record = MongoAccountRepository._record({
        "public_id": "account-1", "email": "member@example.com", "password_hash": "encoded",
        "date_joined": naive_time, "is_staff": True, "is_superuser": True,
        "is_suspended": True, "two_factor_enabled": True, "two_factor_secret": "secret",
        "two_factor_backup_codes": ["RECOVERY"],
        "groups": [{"id": "4", "name": "coaches", "permissions": [{
            "id": "7", "codename": "view_course", "name": "Can view course",
            "app_label": "courses", "model": "course",
        }]}],
        "direct_permissions": [],
        "profile": {
            "bio": "Instructor", "phone": "555", "timezone": "Asia/Kolkata",
            "notification_email": False, "notification_new_lecture": True,
            "notification_course_updates": False, "created_at": naive_time, "updated_at": naive_time,
        },
        "verification_tokens": [{
            "id": "verify-1", "token": "verify-token", "created_at": naive_time,
            "expires_at": naive_time, "used_at": None,
        }],
        "password_reset_tokens": [{
            "id": "reset-1", "token": "reset-token", "created_at": naive_time,
            "expires_at": naive_time, "used_at": None, "ip_address": "192.0.2.1",
        }],
    })

    assert record.is_staff and record.is_superuser and record.is_suspended
    assert record.date_joined == naive_time.replace(tzinfo=timezone.utc)
    assert record.groups[0].permissions[0].codename == "view_course"
    assert record.profile.bio == "Instructor"
    assert record.profile.notification_email is False
    assert record.verification_tokens[0].token == "verify-token"
    assert record.password_reset_tokens[0].ip_address == "192.0.2.1"
