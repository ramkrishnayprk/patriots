import { createTheme } from "@mui/material/styles";

// Cinebot — cinematic dark: marquee gold + crimson on near-black.
export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#F2B134",
      dark: "#C68F1F",
      light: "#F6C665",
      contrastText: "#1A1206",
    },
    secondary: {
      main: "#E63946",
      dark: "#B5202C",
      light: "#F16B76",
      contrastText: "#FFFFFF",
    },
    background: {
      default: "#0B0B0F",
      paper: "#16161C",
    },
    text: {
      primary: "#F5F5F2",
      secondary: "#A6A6B3",
    },
  },
  shape: {
    borderRadius: 10,
  },
  typography: {
    fontFamily: [
      "-apple-system",
      "BlinkMacSystemFont",
      '"Segoe UI"',
      "Roboto",
      '"Helvetica Neue"',
      "Arial",
      "sans-serif",
    ].join(","),
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
      },
    },
  },
});
