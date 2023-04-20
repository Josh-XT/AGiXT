import { useState, useContext, useEffect } from "react";
import {
  List,
  ListItem,
  ListItemButton,
  Typography,
  Switch
} from "@mui/material";
import { URIContext } from "./App";
import AgentCommand from "./AgentCommand";

const AgentCommandsList = ({ agent }) => {
  const baseURI = useContext(URIContext);
  const [allToggled, setAllToggled] = useState(false);
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    updateCommands();
  }, []);
  useEffect(() => {
    setAllToggled(commands.every((command) => command.enabled));
    setLoading(false);
  }, [commands]);

  const updateCommands = async () => {
    try {
      const commands = await (await fetch(`${baseURI}/api/get_commands/${agent}`)).json();
      console.log(commands);
      setCommands([{friendly_name: "All Commands", command_name: "all", enabled: allToggled, command_args: {}}, ...commands.commands.sort()]);
    } catch (error) {
      console.error("Error Fetching Commands:\n", error);
      setCommands([]);
    }
  }

  console.log(commands);
  return (
    loading ? <></> :
    <List dense>
      {commands.map((command) => (
        <AgentCommand key={command.name} {...command} agent={agent} refresh={updateCommands}/>
        ))}
    </List>
  );
};

export default AgentCommandsList;