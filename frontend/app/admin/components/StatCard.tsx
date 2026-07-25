import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import type { SvgIconTypeMap } from "@mui/material/SvgIcon";
import type { OverridableComponent } from "@mui/material/OverridableComponent";

interface Props {
  label: string;
  value: string | number;
  icon: OverridableComponent<SvgIconTypeMap>;
}

export default function StatCard({ label, value, icon: Icon }: Props) {
  return (
    <Paper elevation={0} sx={{ p: 2.5, borderRadius: 3, border: "1px solid", borderColor: "divider", flex: 1, minWidth: 180 }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: 2,
            bgcolor: "rgba(242,177,52,0.12)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "primary.main",
          }}
        >
          <Icon fontSize="small" />
        </Box>
        <Stack>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            {value}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {label}
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}
