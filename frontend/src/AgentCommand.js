import { useState, useContext, useEffect } from "react";
import {
  ListItem,
  ListItemButton,
  Typography,
  Switch,
  Divider,
  TextField,
  Button
} from "@mui/material";
import { URIContext } from "./App";

const AgentCommandsList = ({friendly_name, name, args, enabled, agent, refresh}) => {
  const baseURI = useContext(URIContext);
  const [open, setOpen] = useState(false);
  const [theArgs, setTheArgs] = useState({...args});
  const handleToggleCommand = async () => {
    const endpoint = name === "all" ?
      `${baseURI}/api/${enabled ? "disable" : "enable"}_all_commands/${agent}`:
      `${baseURI}/api/${enabled ? "disable" : "enable"}_command/${agent}`;

      console.log(endpoint)
    fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({command_name: friendly_name})
    }).then(() => refresh());
  };

  const handleSaveArgs = async () => {
    fetch(`${baseURI}/api/command/${name}/config`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: theArgs
    }).then(() => refresh());
  };

  return (
      <>
          <ListItem key={name} disablePadding >
            <ListItemButton onClick={() => setOpen((old) => !old)}>
              <Typography variant="body2">
                {friendly_name}
              </Typography>
            </ListItemButton>
            <Switch
              checked={enabled}
              onChange={() => handleToggleCommand(name)}
              inputProps={{ "aria-label": "Enable/Disable Command" }}
            />
          </ListItem>
          {open? 
          <>
            <Divider />
              {Object.keys(args).map((arg) => <ListItem key={arg}>
              <TextField
                label={arg}
                value={theArgs[arg]}
                onChange={(e) => {
                  const newArgs = {...theArgs};
                  newArgs[arg] = e.target.value;
                  setTheArgs(newArgs);
                }}
              />
              </ListItem>)}
              <ListItem>
                <Button variant="contained" color="primary" onClick={handleSaveArgs} >Save Changes</Button>
              </ListItem>
            <Divider />
            </>
          :null}
        </>
  );
};

export default AgentCommandsList;