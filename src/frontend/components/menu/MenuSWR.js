import {
  ListItem,
  ListItemText,
  Typography
} from "@mui/material";
export default function MenuSWR({ swr, menu }) {
  return (
    swr.isLoading
      ?
      <ListItem>
        <ListItemText>
          <Typography variant="h6" component="h1" noWrap sx={{ fontWeight: "bold" }}>
            Loading...
          </Typography>
        </ListItemText>
      </ListItem>
      :
      (
        swr.error
          ?
          <>
            <ListItem>
              <ListItemText>
                <Typography variant="h6" component="h1" noWrap sx={{ fontWeight: "bold" }}>
                  Error!
                </Typography>
              </ListItemText>
            </ListItem>
            <ListItem>
              <ListItemText>
                <Typography variant="h6" component="h1" noWrap sx={{ fontWeight: "bold" }}>
                  {swr.error.message}
                </Typography>
              </ListItemText>
            </ListItem>
          </>
          :
          menu({ data: swr.data })
      )
  );
}