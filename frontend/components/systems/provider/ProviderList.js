import Link from 'next/link'
import {
  List,
  ListItemText,
  ListItemButton,
  ListItemIcon,
  Divider
} from "@mui/material";
import {
  Home,
  SmartToy
} from "@mui/icons-material";
import { useRouter } from 'next/router';
export default function ProviderList({ data }) {
  const router = useRouter();
  console.log(data);
  return (
    <List>
      <ListItemButton selected={ router.pathname.split("/")[1]=="provider"&&!router.query.provider }>
          <ListItemIcon>
            <Home />
          </ListItemIcon>
          <Link href={`/provider`}>
            <ListItemText primary="Provider Homepage" />
          </Link>
        </ListItemButton>
      <Divider />
      {Object.keys(data).map((provider) => {
          console.log(data[provider])
          return <ListItemButton key={provider} selected={router.query.provider==provider}>
            <ListItemIcon>
              <SmartToy />
            </ListItemIcon>
            <Link href={`/provider/${provider}`}>
              <ListItemText primary={(data[provider])} />
            </Link>
          </ListItemButton>
})}
    </List>
  );
}