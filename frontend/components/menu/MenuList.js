import Link from 'next/link'
import {
  List,
  ListItemText,
  ListItemButton,
  ListItemIcon,
} from "@mui/material";
import {useRouter} from 'next/router';
export default function MenuList({ pages }) {
  const router = useRouter();
  return (
    <List>
      {pages.map(({name, href, Icon}) => (
          <ListItemButton key={name} selected={router.pathname.split("/")[1]==href}>
            <ListItemIcon>
              <Icon />
            </ListItemIcon>
            <Link href={`/${href}`}>
              <ListItemText primary={name} />
            </Link>
          </ListItemButton>
      ))}
    </List>
  );
}