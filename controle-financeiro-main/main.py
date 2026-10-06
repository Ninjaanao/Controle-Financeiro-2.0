from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import os
from contextlib import contextmanager
import base64
import hashlib
import hmac
import json

try:
    from passlib.context import CryptContext
    from jose import jwt, JWTError
except ImportError:
    CryptContext = None

    class JWTError(Exception):
        pass

    class SimpleJWT:
        @staticmethod
        def encode(payload, secret, algorithm="HS256"):
            data = payload.copy()
            exp = data.get("exp")
            if isinstance(exp, datetime):
                data["exp"] = exp.timestamp()
            raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
            body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            return f"local.{body}.{sig}"

        @staticmethod
        def decode(token, secret, algorithms=None):
            try:
                prefix, body, sig = token.split(".", 2)
                if prefix != "local":
                    raise JWTError()
                expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(sig, expected):
                    raise JWTError()
                raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
                data = json.loads(raw.decode())
                if data.get("exp") and datetime.utcnow().timestamp() > data["exp"]:
                    raise JWTError()
                return data
            except Exception as exc:
                raise JWTError() from exc

    jwt = SimpleJWT()

SECRET = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
ALGORITHM = "HS256"
TOKEN_HOURS = 72
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH = os.getenv("DB_PATH", "/tmp/financeiro.db")
USE_PG = bool(DATABASE_URL)
INIT_ADMIN_USER = os.getenv("INIT_ADMIN_USER", "admin").strip().lower()
INIT_ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD", "admin123")
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
if CryptContext:
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
else:
    class LocalPassword:
        @staticmethod
        def hash(password):
            salt = os.urandom(16).hex()
            digest = hashlib.sha256((salt + password).encode()).hexdigest()
            return f"local_sha256${salt}${digest}"

        @staticmethod
        def verify(password, hashed):
            if not hashed.startswith("local_sha256$"):
                return False
            _, salt, digest = hashed.split("$", 2)
            check = hashlib.sha256((salt + password).encode()).hexdigest()
            return hmac.compare_digest(check, digest)

    pwd = LocalPassword()
security = HTTPBearer()
app = FastAPI(title="Controle Financeiro API")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def _pg():
    import psycopg2
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return psycopg2.connect(url)

@contextmanager
def db():
    if USE_PG:
        conn = _pg()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

def q(sql):
    return sql.replace("?", "%s") if USE_PG else sql

def fetchone(cur):
    row = cur.fetchone()
    if row is None:
        return None
    if USE_PG:
        return dict(zip([d[0] for d in cur.description], row))
    return dict(row)

def fetchall(cur):
    rows = cur.fetchall()
    if USE_PG:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]

def init_db():
    with db() as conn:
        cur = conn.cursor()
        if USE_PG:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL, nome TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'usuario');
            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT NOT NULL, UNIQUE(nome, tipo));
            CREATE TABLE IF NOT EXISTS transacoes (
                id SERIAL PRIMARY KEY, data TEXT NOT NULL, tipo TEXT NOT NULL, categoria TEXT NOT NULL,
                descricao TEXT NOT NULL, valor DOUBLE PRECISION NOT NULL, pagamento TEXT DEFAULT 'Pix',
                obs TEXT DEFAULT '', usuario TEXT NOT NULL, usuario_nome TEXT NOT NULL,
                criado_em TIMESTAMP DEFAULT NOW());
            """)
        else:
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL, nome TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'usuario');
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, tipo TEXT NOT NULL, UNIQUE(nome, tipo));
            CREATE TABLE IF NOT EXISTS transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, tipo TEXT NOT NULL, categoria TEXT NOT NULL,
                descricao TEXT NOT NULL, valor REAL NOT NULL, pagamento TEXT DEFAULT 'Pix',
                obs TEXT DEFAULT '', usuario TEXT NOT NULL, usuario_nome TEXT NOT NULL,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
            """)
        cur.execute(q("SELECT COUNT(*) AS c FROM users"))
        row = fetchone(cur)
        if (row["c"] if row else 0) == 0:
            cur.execute(q("INSERT INTO users (username, senha_hash, nome, role) VALUES (?,?,?,?)"),
                        (INIT_ADMIN_USER, pwd.hash(INIT_ADMIN_PASSWORD), "Administrador", "admin"))
            cur.execute(q("INSERT INTO users (username, senha_hash, nome, role) VALUES (?,?,?,?)"),
                        ("financeiro", pwd.hash("fin123"), "Equipe Financeiro", "usuario"))
            defaults = [
                ("Vendas de Produtos","Receita"),("Prestação de Serviços","Receita"),
                ("Comissões","Receita"),("Outras Receitas","Receita"),
                ("Salários e Encargos","Despesa"),("Aluguel / Condomínio","Despesa"),
                ("Energia Elétrica","Despesa"),("Internet / Telefone","Despesa"),
                ("Marketing e Publicidade","Despesa"),("Impostos e Taxas","Despesa"),
                ("Software / Assinaturas","Despesa"),("Outras Despesas","Despesa"),
            ]
            for nome, tipo in defaults:
                cur.execute(q("INSERT INTO categorias (nome, tipo) VALUES (?,?)"), (nome, tipo))

init_db()

class LoginIn(BaseModel):
    username: str
    senha: str
class UserCreate(BaseModel):
    username: str
    senha: str
    nome: str
    role: str = "usuario"
class CatIn(BaseModel):
    nome: str
    tipo: str
class TransIn(BaseModel):
    data: str
    tipo: str
    categoria: str
    descricao: str
    valor: float = Field(gt=0)
    pagamento: str = "Pix"
    obs: str = ""

def create_token(user):
    return jwt.encode({"sub": user["username"], "uid": user["id"], "role": user["role"],
        "nome": user["nome"], "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS)}, SECRET, algorithm=ALGORITHM)

def get_current(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return jwt.decode(creds.credentials, SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

def require_admin(user=Depends(get_current)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores")
    return user

@app.post("/api/login")
def login(body: LoginIn):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("SELECT * FROM users WHERE username = ?"), (body.username.strip().lower(),))
        row = fetchone(cur)
    if not row or not pwd.verify(body.senha, row["senha_hash"]):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    return {"token": create_token(row), "user": {"id": row["id"], "username": row["username"], "nome": row["nome"], "role": row["role"]}}

@app.get("/api/me")
def me(user=Depends(get_current)):
    return {"username": user["sub"], "nome": user["nome"], "role": user["role"]}

@app.get("/api/users")
def list_users(_=Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, nome, role FROM users ORDER BY id")
        return fetchall(cur)

@app.post("/api/users")
def create_user(body: UserCreate, _=Depends(require_admin)):
    un = body.username.strip().lower()
    with db() as conn:
        cur = conn.cursor()
        try:
            cur.execute(q("INSERT INTO users (username, senha_hash, nome, role) VALUES (?,?,?,?)"),
                        (un, pwd.hash(body.senha), body.nome.strip(), body.role))
            if USE_PG:
                cur.execute("SELECT lastval()"); uid = cur.fetchone()[0]
            else:
                uid = cur.lastrowid
            return {"id": uid, "username": un, "nome": body.nome.strip(), "role": body.role}
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(400, "Usuário já existe")
            raise

@app.delete("/api/users/{uid}")
def delete_user(uid: int, user=Depends(require_admin)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("SELECT username FROM users WHERE id=?"), (uid,))
        row = fetchone(cur)
        if not row: raise HTTPException(404, "Usuário não encontrado")
        if row["username"] in ("admin", user["sub"]): raise HTTPException(400, "Não é possível remover este usuário")
        cur.execute(q("DELETE FROM users WHERE id=?"), (uid,))
    return {"ok": True}

@app.get("/api/categorias")
def list_cats(user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome")
        return fetchall(cur)

@app.post("/api/categorias")
def create_cat(body: CatIn, user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        try:
            cur.execute(q("INSERT INTO categorias (nome, tipo) VALUES (?,?)"), (body.nome.strip(), body.tipo))
            if USE_PG:
                cur.execute("SELECT lastval()"); cid = cur.fetchone()[0]
            else:
                cid = cur.lastrowid
            return {"id": cid, "nome": body.nome.strip(), "tipo": body.tipo}
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(400, "Categoria já existe")
            raise

@app.put("/api/categorias/{cid}")
def rename_cat(cid: int, body: CatIn, user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("SELECT * FROM categorias WHERE id=?"), (cid,))
        old = fetchone(cur)
        if not old: raise HTTPException(404, "Não encontrada")
        cur.execute(q("UPDATE categorias SET nome=? WHERE id=?"), (body.nome.strip(), cid))
        cur.execute(q("UPDATE transacoes SET categoria=? WHERE categoria=? AND tipo=?"),
                    (body.nome.strip(), old["nome"], old["tipo"]))
    return {"ok": True}

@app.delete("/api/categorias/{cid}")
def delete_cat(cid: int, user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("DELETE FROM categorias WHERE id=?"), (cid,))
    return {"ok": True}

@app.get("/api/transacoes")
def list_trans(user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, data, tipo, categoria, descricao, valor, pagamento, obs, usuario, usuario_nome FROM transacoes ORDER BY data DESC, id DESC")
        return fetchall(cur)

@app.post("/api/transacoes")
def create_trans(body: TransIn, user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("INSERT INTO transacoes (data, tipo, categoria, descricao, valor, pagamento, obs, usuario, usuario_nome) VALUES (?,?,?,?,?,?,?,?,?)"),
            (body.data, body.tipo, body.categoria, body.descricao.strip(), body.valor, body.pagamento, body.obs or "", user["sub"], user["nome"]))
        if USE_PG:
            cur.execute("SELECT lastval()"); rid = cur.fetchone()[0]
        else:
            rid = cur.lastrowid
        cur.execute(q("SELECT id, data, tipo, categoria, descricao, valor, pagamento, obs, usuario, usuario_nome FROM transacoes WHERE id=?"), (rid,))
        return fetchone(cur)

@app.put("/api/transacoes/{tid}")
def update_trans(tid: int, body: TransIn, user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("SELECT id FROM transacoes WHERE id=?"), (tid,))
        if not fetchone(cur): raise HTTPException(404, "Não encontrada")
        cur.execute(q("UPDATE transacoes SET data=?, tipo=?, categoria=?, descricao=?, valor=?, pagamento=?, obs=? WHERE id=?"),
            (body.data, body.tipo, body.categoria, body.descricao.strip(), body.valor, body.pagamento, body.obs or "", tid))
        cur.execute(q("SELECT id, data, tipo, categoria, descricao, valor, pagamento, obs, usuario, usuario_nome FROM transacoes WHERE id=?"), (tid,))
        return fetchone(cur)

@app.delete("/api/transacoes/{tid}")
def delete_trans(tid: int, user=Depends(get_current)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q("DELETE FROM transacoes WHERE id=?"), (tid,))
    return {"ok": True}

@app.get("/api/health")
def health():
    return {"status": "ok", "db": "postgres" if USE_PG else "sqlite", "time": datetime.utcnow().isoformat()}

FRONTEND = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(FRONTEND):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND, "index.html"))
