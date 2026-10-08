import pytest

from emerager0db.auth.passwords import hash_password, validate_password, verify_password
from emerager0db.auth.permissions import Permission
from emerager0db.auth.users import UserStore
from emerager0db.engine.catalog import Catalog
from emerager0db.errors import (
    AuthenticationError,
    PermissionDeniedError,
    UserError,
)
from emerager0db.session import Connection


def test_passwords_are_salted_and_verifiable():
    encoded = hash_password("correct horse battery")
    assert "correct horse battery" not in encoded
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("wrong password value", encoded)
    assert hash_password("samepassword!") != hash_password("samepassword!")


def test_short_passwords_are_rejected():
    with pytest.raises(UserError):
        validate_password("short")


@pytest.fixture
def system(tmp_path):
    catalog = Catalog(tmp_path / "data")
    catalog.ensure_layout()
    users = UserStore(catalog.system_dir / "users.json")
    users.create("root", "rootpassword", {Permission.ADMIN.value}, root=True)
    users.create("alice", "alicepassword")
    users.create("bob", "bobpassword")
    root = Connection.login(catalog, users, "root", "rootpassword")
    return catalog, users, root


def test_user_file_never_contains_plaintext(system):
    catalog, _, _ = system
    raw = (catalog.system_dir / "users.json").read_bytes()
    assert b"rootpassword" not in raw
    assert b"alicepassword" not in raw


def test_wrong_password_and_unknown_user_share_one_message(system):
    catalog, users, _ = system
    with pytest.raises(AuthenticationError, match="invalid username or password"):
        Connection.login(catalog, users, "alice", "nope-not-it")
    with pytest.raises(AuthenticationError, match="invalid username or password"):
        Connection.login(catalog, users, "ghost", "nope-not-it")


def test_root_cannot_be_deleted_and_last_admin_is_protected(system):
    _, users, _ = system
    with pytest.raises(UserError):
        users.delete("root")
    with pytest.raises(UserError):
        users.revoke("root", Permission.ADMIN.value)


def test_normal_users_are_restricted_by_permissions(system):
    catalog, users, root = system
    root.execute("CREATE DATABASE school;")
    root.execute("USE school;")
    root.execute("CREATE TABLE grades (id INTEGER, score INTEGER);")
    root.execute("INSERT INTO grades VALUES (1, 90);")

    users.grant("alice", Permission.DATABASE_CREATE.value)
    alice = Connection.login(catalog, users, "alice", "alicepassword")
    with pytest.raises(PermissionDeniedError):
        alice.execute("USE school;")
    with pytest.raises(PermissionDeniedError):
        alice.execute("DROP DATABASE school;")
    with pytest.raises(PermissionDeniedError):
        alice.create_user("eve", "evepassword")

    root.execute("GRANT READ ON school TO alice;")
    alice.execute("USE school;")
    assert alice.execute("SELECT COUNT(*) FROM grades;").fetchone() == (1,)
    with pytest.raises(PermissionDeniedError):
        alice.execute("INSERT INTO grades VALUES (2, 80);")
    with pytest.raises(PermissionDeniedError):
        alice.execute("DROP TABLE grades;")
    with pytest.raises(PermissionDeniedError):
        alice.execute("GRANT WRITE ON school TO alice;")

    root.execute("GRANT WRITE ON school TO alice;")
    alice.execute("INSERT INTO grades VALUES (2, 80);")
    assert alice.execute("SELECT COUNT(*) FROM grades;").fetchone() == (2,)


def test_users_manage_their_own_databases(system):
    catalog, users, root = system
    users.grant("alice", Permission.DATABASE_CREATE.value)
    alice = Connection.login(catalog, users, "alice", "alicepassword")
    alice.execute("CREATE DATABASE notes;")
    alice.execute("USE notes;")
    alice.execute("CREATE TABLE memo (id INTEGER);")
    alice.execute("DROP TABLE memo;")
    alice.execute("DROP DATABASE notes;")
    assert not catalog.exists("notes")


def test_password_self_service_requires_current_password(system):
    catalog, users, _ = system
    alice = Connection.login(catalog, users, "alice", "alicepassword")
    with pytest.raises(AuthenticationError):
        alice.change_password("alice", "newalicepass", current_password="wrongcurrent")
    with pytest.raises(PermissionDeniedError):
        alice.change_password("root", "hijacked-root", current_password="alicepassword")
    alice.change_password("alice", "newalicepass", current_password="alicepassword")
    assert Connection.login(catalog, users, "alice", "newalicepass") is not None


def test_backup_is_verified_and_importable(system, tmp_path):
    catalog, _, root = system
    root.execute("CREATE DATABASE archive;")
    root.execute("USE archive;")
    root.execute("CREATE TABLE logs (msg TEXT);")
    root.execute("INSERT INTO logs VALUES ('boot');")
    catalog.backup_database("archive", tmp_path / "archive.bak")
    catalog.import_database(tmp_path / "archive.bak", owner="root", name="archive_restored")
    root.execute("USE archive_restored;")
    assert root.execute("SELECT msg FROM logs;").fetchall() == [("boot",)]
