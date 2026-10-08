# Getting started

## 1. Install

Linux and macOS:

```sh
curl -fsSL https://falks.cyou/get | sh
```

Windows (PowerShell):

```powershell
irm https://falks.cyou/get.ps1 | iex
```

The installer checks the SHA-256 of the download against the published checksum before it installs anything. It then runs the setup wizard.

## 2. Create the root account

The first run asks for a root username and password. Root is the administrator. You can also create normal users during setup. Passwords are never printed or stored in plain text. `Emerager0DB setup` only works while no accounts exist. After that, use `.adduser` from the shell.

## 3. Start the shell

```sh
Emerager0DB
```

Log in with the username and password you chose. The prompt shows your username.

## 4. Make your first database

```sql
CREATE DATABASE school;
USE school;
CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER);
INSERT INTO students VALUES (1, 'Rrs', NULL);
SELECT * FROM students;
```

Statements end with a semicolon. The shell waits for the semicolon, so one statement can span several lines.

## 5. Stop and come back

Type `.exit`. Your data is saved after every statement, so there is nothing else to do. Start the shell again and `USE school;` to continue.

Where data lives:

- Linux and macOS: `~/.emerager0db/`
- Windows: `%USERPROFILE%\.emerager0db\`

Override with `EMERAGER0DB_HOME` or `--data-dir`.
