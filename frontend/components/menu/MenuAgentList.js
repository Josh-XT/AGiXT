import Link from 'next/link'
import {
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  ListItemIcon,
  Divider
} from "@mui/material";
import {
  RunCircle, 
  StopCircle, 
  AddCircle
} from "@mui/icons-material";
export default function MenuAgentList({ data }) {
  return (
    <List>
      <ListItem disablePadding>
        <ListItemButton>
          <ListItemIcon>
            <AddCircle />
          </ListItemIcon>
          <Link href={`/new_agent`}>
            <ListItemText primary="Add A New Agent" />
          </Link>
        </ListItemButton>
      </ListItem>
      <Divider />
      {data.map((agent) => (
        <ListItem key={agent.name} disablePadding>
          <ListItemButton>
            <ListItemIcon>
              {agent.status ? <RunCircle /> : <StopCircle />}
            </ListItemIcon>
            <Link href={`/agent/${agent.name}`}>
              <ListItemText primary={agent.name} />
            </Link>
          </ListItemButton>
        </ListItem>
      ))}
    </List>
  );
}