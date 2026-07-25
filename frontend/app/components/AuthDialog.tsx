"use client";

import { useEffect, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Collapse from "@mui/material/Collapse";
import Link from "@mui/material/Link";
import CircularProgress from "@mui/material/CircularProgress";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";
import { createUser, login, type CurrentUser } from "@/lib/auth";

type Mode = "signup" | "login";

interface AuthDialogProps {
  open: boolean;
  initialMode: Mode;
  onClose: () => void;
  onSuccess: (user: CurrentUser) => void;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const USERNAME_RE = /^[a-zA-Z0-9_]{3,20}$/;

export default function AuthDialog({ open, initialMode, onClose, onSuccess }: AuthDialogProps) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMode(initialMode);
    resetForm();
  }, [open, initialMode]);

  function resetForm() {
    setFirstName("");
    setLastName("");
    setUsername("");
    setEmail("");
    setIdentifier("");
    setPassword("");
    setConfirmPassword("");
    setShowPassword(false);
    setFieldErrors({});
    setFormError(null);
    setSubmitting(false);
  }

  function switchMode(next: Mode) {
    setMode(next);
    resetForm();
  }

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (mode === "signup") {
      if (!firstName.trim()) errors.firstName = "Required";
      if (!lastName.trim()) errors.lastName = "Required";
      if (!USERNAME_RE.test(username.trim())) errors.username = "3-20 characters, letters/numbers/underscore only";
      if (!EMAIL_RE.test(email.trim())) errors.email = "Enter a valid email address";
      if (password.length < 8) errors.password = "At least 8 characters";
      else if (confirmPassword !== password) errors.confirmPassword = "Passwords don't match";
    } else {
      if (!identifier.trim()) errors.identifier = "Required";
      if (!password) errors.password = "Required";
    }
    return errors;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    const result =
      mode === "signup"
        ? await createUser({ firstName, lastName, username, email, password })
        : await login(identifier, password);
    setSubmitting(false);

    if (!result.ok) {
      if (mode === "signup" && result.error.includes("Username")) {
        setFieldErrors((f) => ({ ...f, username: result.error }));
      } else if (mode === "signup" && result.error.includes("Email")) {
        setFieldErrors((f) => ({ ...f, email: result.error }));
      } else {
        setFormError(result.error);
      }
      return;
    }

    onSuccess(result.data);
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="xs"
      fullWidth
      slotProps={{
        paper: {
          sx: {
            bgcolor: "rgba(22,22,28,0.92)",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 3,
            backgroundImage: "none",
          },
        },
        backdrop: {
          sx: { backdropFilter: "blur(4px)", bgcolor: "rgba(0,0,0,0.6)" },
        },
      }}
    >
      <Box component="form" noValidate onSubmit={handleSubmit}>
        <DialogContent sx={{ p: 4 }}>
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 1 }}>
            <Box
              sx={{
                width: 44,
                height: 44,
                borderRadius: 2,
                bgcolor: "rgba(242,177,52,0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "primary.main",
              }}
            >
              <ForumRoundedIcon />
            </Box>
            <IconButton size="small" onClick={onClose} sx={{ color: "text.secondary" }}>
              <CloseRoundedIcon fontSize="small" />
            </IconButton>
          </Stack>

          <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
            {mode === "signup" ? "Create your account" : "Welcome back"}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            {mode === "signup" ? "Sign up to start chatting with Cinebot." : "Log in to continue chatting with Cinebot."}
          </Typography>

          <Stack spacing={2}>
            <Collapse in={mode === "signup"} unmountOnExit>
              <Stack direction="row" spacing={2}>
                <TextField
                  autoFocus={mode === "signup"}
                  fullWidth
                  label="First name"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  error={Boolean(fieldErrors.firstName)}
                  helperText={fieldErrors.firstName}
                  disabled={submitting}
                />
                <TextField
                  fullWidth
                  label="Last name"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  error={Boolean(fieldErrors.lastName)}
                  helperText={fieldErrors.lastName}
                  disabled={submitting}
                />
              </Stack>
            </Collapse>

            {mode === "signup" ? (
              <>
                <TextField
                  fullWidth
                  label="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  error={Boolean(fieldErrors.username)}
                  helperText={fieldErrors.username ?? "You'll use this to log in"}
                  disabled={submitting}
                />
                <TextField
                  fullWidth
                  type="email"
                  label="Email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  error={Boolean(fieldErrors.email)}
                  helperText={fieldErrors.email}
                  disabled={submitting}
                />
              </>
            ) : (
              <TextField
                autoFocus
                fullWidth
                label="Username or email"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                error={Boolean(fieldErrors.identifier)}
                helperText={fieldErrors.identifier}
                disabled={submitting}
              />
            )}

            <TextField
              fullWidth
              type={showPassword ? "text" : "password"}
              label="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={Boolean(fieldErrors.password)}
              helperText={fieldErrors.password}
              disabled={submitting}
              slotProps={{
                input: {
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton size="small" onClick={() => setShowPassword((v) => !v)} tabIndex={-1}>
                        {showPassword ? (
                          <VisibilityOffRoundedIcon fontSize="small" />
                        ) : (
                          <VisibilityRoundedIcon fontSize="small" />
                        )}
                      </IconButton>
                    </InputAdornment>
                  ),
                },
              }}
            />

            <Collapse in={mode === "signup"} unmountOnExit>
              <TextField
                fullWidth
                type={showPassword ? "text" : "password"}
                label="Confirm password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                error={Boolean(fieldErrors.confirmPassword)}
                helperText={fieldErrors.confirmPassword}
                disabled={submitting}
              />
            </Collapse>

            {formError && <Alert severity="error">{formError}</Alert>}

            <Button
              type="submit"
              variant="contained"
              color="primary"
              size="large"
              disabled={submitting}
              sx={{ py: 1.25 }}
            >
              {submitting ? (
                <CircularProgress size={18} sx={{ color: "primary.contrastText" }} />
              ) : mode === "signup" ? (
                "Create account"
              ) : (
                "Log in"
              )}
            </Button>

            <Typography variant="body2" sx={{ textAlign: "center", color: "text.secondary" }}>
              {mode === "signup" ? (
                <>
                  Already have an account?{" "}
                  <Link component="button" type="button" onClick={() => switchMode("login")} sx={{ color: "primary.light" }}>
                    Log in
                  </Link>
                </>
              ) : (
                <>
                  New here?{" "}
                  <Link component="button" type="button" onClick={() => switchMode("signup")} sx={{ color: "primary.light" }}>
                    Create an account
                  </Link>
                </>
              )}
            </Typography>

            <Typography variant="caption" sx={{ textAlign: "center", color: "text.secondary", opacity: 0.7 }}>
              Demo account — stored only in this browser, not sent anywhere.
            </Typography>
          </Stack>
        </DialogContent>
      </Box>
    </Dialog>
  );
}
