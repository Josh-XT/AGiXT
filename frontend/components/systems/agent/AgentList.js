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
  AddCircle,
  Home
} from "@mui/icons-material";
import { useRouter } from 'next/router';
export default function MenuAgentList({ data }) {
  const router = useRouter();
  console.log(data);
  return (
    <List>
      <ListItemButton selected={ router.pathname.split("/")[1]=="agent"&&!router.query.agent }>
          <ListItemIcon>
            <Home />
          </ListItemIcon>
          <Link href={`/agent`}>
            <ListItemText primary="Agent Homepage" />
          </Link>
        </ListItemButton>
        <ListItemButton selected={  router.pathname.split("/")[1]=="new" && router.pathname.split("/")[2]=="agent"}>
          <ListItemIcon>
            <AddCircle />
          </ListItemIcon>
          <Link href={`/new/agent`}>
            <ListItemText primary="Add A New Agent" />
          </Link>
        </ListItemButton>
      <Divider />
      {data.map((agent) => (
          <ListItemButton key={agent.name} selected={router.query.agent==agent.name}>
            <ListItemIcon>
              {agent.status ? <RunCircle /> : <StopCircle />}
            </ListItemIcon>
            <Link href={`/agent/${agent.name}`}>
              <ListItemText primary={agent.name} />
            </Link>
          </ListItemButton>
      ))}
    </List>
  );
}