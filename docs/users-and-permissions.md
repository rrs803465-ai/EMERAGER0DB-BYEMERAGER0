# Users and permissions

## Accounts

- The first account is **root**, the administrator. Root cannot be deleted.
- Administrators can create and delete accounts, reset passwords, and do anything else.
- Normal users are created by an administrator with `.adduser` (or during setup).
- Every user can change their own password with `.passwd`, after entering the current one.
- The last administrator cannot be deleted or demoted.

Usernames are lowercase, start with a letter, and may contain digits, `_`, `.` and `-`. Passwords must be at least 8 characters.

## How passwords are stored

Passwords are hashed with PBKDF2-HMAC-SHA256 using a random 16-byte salt and 600,000 iterations (configurable with `EMERAGER0DB_PBKDF2_ITERATIONS`). The file stores only the hash. Login failures give the same message whether the username or the password was wrong.

## Global permissions

| Permission | Allows |
| --- | --- |
| `ADMIN` | Everything. Root has it. |
| `USER_MANAGE` | Create, delete and reset accounts |
| `DATABASE_CREATE` | Create databases |
| `DATABASE_DROP` | Drop databases that are not owned by an administrator |
| `DATABASE_READ` | Read any database |
| `DATABASE_WRITE` | Write to any database |
| `TABLE_CREATE` | Create tables in any database |
| `TABLE_DROP` | Drop tables that are not owned by an administrator |

Global permissions belong to accounts. The shell can create an administrator (`.adduser` asks). Other global permissions are set through the account store API (`UserStore.grant`), which is not yet a shell command in 0.1 beta.

## Per-database grants

The owner of a database has every right on it. Other users need grants:

```sql
GRANT READ ON school TO alice;        -- read tables
GRANT WRITE ON school TO alice;       -- insert, update, delete
GRANT TABLE_CREATE ON school TO alice;
GRANT TABLE_DROP ON school TO alice;
REVOKE WRITE ON school FROM alice;
```

Only the database owner or an administrator can manage grants.

## Ownership rules

| Action | Who may do it |
| --- | --- |
| Drop a database | Its owner or an administrator. Users cannot drop a root-owned database. |
| Drop a table | Its owner, or the database owner, or a user with `TABLE_DROP`. Users cannot drop a root-owned table. |
| Read or write rows | The owner, a user with the matching grant, or a holder of the matching global permission |

A normal user who creates a table owns it. A user who creates a database owns it.

## Example

```sql
-- as root
CREATE DATABASE school;
USE school;
CREATE TABLE grades (id INTEGER, score INTEGER);
GRANT READ ON school TO alice;
```

```sql
-- as alice
USE school;
SELECT * FROM grades;            -- allowed
INSERT INTO grades VALUES (1, 90);   -- Error: permission denied
DROP TABLE grades;                   -- Error: permission denied (root-owned)
```

## The embedded Python API

`connect("file.edb")` opens a file directly, with no login. It is meant for code running as the local operator, not for a shared service. Use the CLI's accounts when more than one person must access data.
