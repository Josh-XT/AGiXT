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
  AddLink,
  InsertLink,
  Home
} from "@mui/icons-material";
import {useRouter} from 'next/router';
export default function MenuChainList({ data }) {
  const router = useRouter();
  console.log(data);
  console.log(data?Object.keys(data):null);
  return (
    <List>
      <ListItemButton key={"home"} selected={ router.pathname.split("/")[1]=="chain"&&!router.query.chain }>
          <ListItemIcon>
            <Home />
          </ListItemIcon>
          <Link href={`/chain`}>
            <ListItemText primary="Chain Homepage" />
          </Link>
        </ListItemButton>
        <ListItemButton key={"new"} selected={  router.pathname.split("/")[1]=="new" && router.pathname.split("/")[2]=="chain"}>
          <ListItemIcon>
            <AddLink />
          </ListItemIcon>
          <Link href={`/new/chain`}>
            <ListItemText primary="Add A New Chain" />
          </Link>
        </ListItemButton>
      <Divider />
      {data.map((chain) => (
          <ListItemButton key={chain}>
            <ListItemIcon>
              <InsertLink />
            </ListItemIcon>
            <Link href={`/chain/${chain}`}>
              <ListItemText primary={chain} />
            </Link>
          </ListItemButton>
      ))}
    </List>
  );
}