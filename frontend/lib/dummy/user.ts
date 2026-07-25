export interface CurrentUser {
  name: string;
  email: string;
  initials: string;
}

// Hardcoded until real auth is wired in — no login flow in this pass.
export const CURRENT_USER: CurrentUser = {
  name: "Maya Chen",
  email: "maya@cinebot.app",
  initials: "MC",
};
