import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr"
import {
  ListItem,
  ListItemButton,
  Typography,
  Switch,
} from "@mui/material";
export default function AgentCommandsList({ friendly_name, name, args, enabled }) {
  const agentName = useRouter().query.agent;
  //const [open, setOpen] = useState(false);
  //const [theArgs, setTheArgs] = useState({...args});
  const handleToggleCommand = async () => {
    await axios.patch(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`, { command_name: friendly_name, enable: enabled? "false" : "true" });
    mutate(`agent/${agentName}/commands`);
  };
  /*
  const handleSaveArgs = async () => {
    fetch(`${baseURI}/api/command/${name}/config`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: theArgs
    }).then(() => refresh());
  };
*/
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
      {/*open? 
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
              :null*/}
    </>
  );
};
