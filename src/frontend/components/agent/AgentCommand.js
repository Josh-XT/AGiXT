import {
  ListItem,
  ListItemButton,
  Typography,
  Switch,
} from "@mui/material";
import axios from "axios";
import { mutate } from "swr"
import { useRouter } from "next/router";
export default function AgentCommandsList ({friendly_name, name, args, enabled}) {
  const agentName = useRouter().query.agent;
  //const [open, setOpen] = useState(false);
  //const [theArgs, setTheArgs] = useState({...args});
  const handleToggleCommand = () => {
    axios.patch(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`, {command_name: friendly_name, enable: data.every((command) => command.enabled)?"false":"true"}).then(() => mutate(`agent/${agentName}/commands`)).then(() => mutate(`agent/${agentName}/commands`));
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
