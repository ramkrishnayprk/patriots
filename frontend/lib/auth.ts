// Client-only, localStorage-backed fake auth — NOT real security. There is
// no backend; passwords are hashed (SHA-256, no salt — there's no server
// secret to salt against) only to avoid literal plaintext sitting in
// localStorage, not to actually protect anything from someone with DevTools
// access. Follows the same localStorage guard/try-catch convention used elsewhere.
// Deliberately exposes only semantic operations (createUser/login), not raw
// load/save, so callers can't bypass uniqueness checks or hashing.

const USERS_KEY = "cinebot:auth-users:v1";
const SESSION_KEY = "cinebot:auth-session:v1";
const WELCOME_PENDING_KEY = "cinebot:welcome-pending";

export interface StoredUser {
  id: string;
  firstName: string;
  lastName: string;
  username: string;
  email: string;
  passwordHash: string;
  createdAt: string;
}

interface StoredSession {
  userId: string;
  createdAt: string;
  guest?: boolean;
}

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  initials: string;
  username: string;
}

export type AuthResult<T> = { ok: true; data: T } | { ok: false; error: string };

function loadUsers(): StoredUser[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(USERS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveUsers(users: StoredUser[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(USERS_KEY, JSON.stringify(users));
  } catch {
    // Private browsing / quota exceeded — signup just won't persist this time.
  }
}

function loadSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

function saveSession(session: StoredSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // ignore
  }
}

function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // ignore
  }
}

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function toCurrentUser(user: StoredUser): CurrentUser {
  const initials = `${user.firstName[0] ?? ""}${user.lastName[0] ?? ""}`.toUpperCase();
  return {
    id: user.id,
    name: `${user.firstName} ${user.lastName}`,
    email: user.email,
    initials,
    username: user.username,
  };
}

export function hasAnyUsers(): boolean {
  return loadUsers().length > 0;
}

export function findUserByIdentifier(identifier: string): StoredUser | null {
  const lower = identifier.trim().toLowerCase();
  const match = loadUsers().find((u) => u.username.toLowerCase() === lower || u.email.toLowerCase() === lower);
  return match ?? null;
}

export async function createUser(input: {
  firstName: string;
  lastName: string;
  username: string;
  email: string;
  password: string;
}): Promise<AuthResult<CurrentUser>> {
  const users = loadUsers();
  const usernameLower = input.username.trim().toLowerCase();
  const emailLower = input.email.trim().toLowerCase();

  if (users.some((u) => u.username.toLowerCase() === usernameLower)) {
    return { ok: false, error: "Username already taken" };
  }
  if (users.some((u) => u.email.toLowerCase() === emailLower)) {
    return { ok: false, error: "Email already registered" };
  }

  const user: StoredUser = {
    id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    firstName: input.firstName.trim(),
    lastName: input.lastName.trim(),
    username: input.username.trim(),
    email: input.email.trim(),
    passwordHash: await sha256Hex(input.password),
    createdAt: new Date().toISOString(),
  };

  saveUsers([...users, user]);
  saveSession({ userId: user.id, createdAt: user.createdAt });
  markWelcomePending();
  return { ok: true, data: toCurrentUser(user) };
}

export async function login(identifier: string, password: string): Promise<AuthResult<CurrentUser>> {
  const user = findUserByIdentifier(identifier);
  if (!user) {
    return { ok: false, error: "Incorrect username/email or password" };
  }
  const hash = await sha256Hex(password);
  if (hash !== user.passwordHash) {
    return { ok: false, error: "Incorrect username/email or password" };
  }
  saveSession({ userId: user.id, createdAt: new Date().toISOString() });
  markWelcomePending();
  return { ok: true, data: toCurrentUser(user) };
}

export function continueAsGuest(): CurrentUser {
  const guest: CurrentUser = {
    id: "guest",
    name: "Guest",
    email: "",
    initials: "G",
    username: "guest",
  };
  saveSession({
    userId: guest.id,
    createdAt: new Date().toISOString(),
    guest: true,
  });
  markWelcomePending();
  return guest;
}

export function logout(): void {
  clearSession();
}

export function getCurrentUser(): CurrentUser | null {
  const session = loadSession();
  if (!session) return null;
  if (session.guest) {
    return {
      id: "guest",
      name: "Guest",
      email: "",
      initials: "G",
      username: "guest",
    };
  }
  const user = loadUsers().find((u) => u.id === session.userId);
  return user ? toCurrentUser(user) : null;
}

export function subscribeToAuthChanges(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  function handler(e: StorageEvent) {
    if (e.key === SESSION_KEY) cb();
  }
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

// One-shot "just signed up/logged in" flag for the welcome toast. Peeking
// does NOT consume it — only clearWelcomePending() (called from the toast's
// onClose) does. Consuming on read caused the toast to disappear before it
// ever rendered when ChatClient's auth-check effect re-ran during the
// post-login navigation/remount.
function markWelcomePending(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(WELCOME_PENDING_KEY, "1");
  } catch {
    // ignore
  }
}

export function isWelcomePending(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(WELCOME_PENDING_KEY) === "1";
  } catch {
    return false;
  }
}

export function clearWelcomePending(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(WELCOME_PENDING_KEY);
  } catch {
    // ignore
  }
}
