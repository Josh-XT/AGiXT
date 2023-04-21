import '@/styles/globals.css'
import { useState, useCallback } from 'react';
import Link from 'next/link';
import axios from 'axios';
import useSWR from 'swr';
import {
  Box,
  Drawer,
  CssBaseline,
  Toolbar,
  List,
  Typography,
  Divider
} from '@mui/material';
import MuiAppBar from '@mui/material/AppBar';
import IconButton from '@mui/material/IconButton';
import { 
  styled, 
  createTheme, 
  ThemeProvider 
} from '@mui/material/styles';
import { 
  ChevronLeft,
  Menu 
} from '@mui/icons-material';
import MenuSWR from '@/components/menu/MenuSWR';
import MenuAgentList from '@/components/menu/MenuAgentList';
import { MenuDarkSwitch } from '@/components/menu/MenuDarkSwitch';
const drawerWidth = 240;
const Main = styled('main', { shouldForwardProp: (prop) => prop !== 'open' })(
  ({ theme, open }) => ({
    flexGrow: 1,
    padding: theme.spacing(3),
    transition: theme.transitions.create('margin', {
      easing: theme.transitions.easing.sharp,
      duration: theme.transitions.duration.leavingScreen,
    }),
    marginLeft: `-${drawerWidth}px`,
    ...(open && {
      transition: theme.transitions.create('margin', {
        easing: theme.transitions.easing.easeOut,
        duration: theme.transitions.duration.enteringScreen,
      }),
      marginLeft: 0,
    }),
  }),
);
const AppBar = styled(MuiAppBar, {
  shouldForwardProp: (prop) => prop !== 'open',
})(({ theme, open }) => ({
  transition: theme.transitions.create(['margin', 'width'], {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  ...(open && {
    width: `calc(100% - ${drawerWidth}px)`,
    marginLeft: `${drawerWidth}px`,
    transition: theme.transitions.create(['margin', 'width'], {
      easing: theme.transitions.easing.easeOut,
      duration: theme.transitions.duration.enteringScreen,
    }),
  }),
}));
const DrawerHeader = styled('div')(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  padding: theme.spacing(0, 1),
  // necessary for content to be below app bar
  ...theme.mixins.toolbar,
  justifyContent: 'flex-end',
  backgroundColor: theme.palette.primary.main,
  color: 'white'
}));
export default function App({ Component, pageProps }) {
  const [open, setOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const agents = useSWR('agents', async () => (await axios.get(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent`)).data.agents);

  const themeGenerator = (darkMode) =>
    createTheme({
      palette: {
        mode: darkMode ? "dark" : "light",
        primary: {
          main: "#273043",
        },
      },
    });
  const theme = themeGenerator(darkMode);

  const handleDrawerOpen = () => {
    setOpen(true);
  };

  const handleDrawerClose = () => {
    setOpen(false);
  };

  const handleToggleDarkMode = useCallback(() => {
    setDarkMode((old) => !old);
  }, []);
  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ display: 'flex' }}>
        <CssBaseline />
        <AppBar position="fixed" open={open}>
          <Toolbar sx={{ display: "flex", justifyContent: "space-between" }}>
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <IconButton
                color="inherit"
                aria-label="open drawer"
                onClick={handleDrawerOpen}
                edge="start"
                sx={{ mr: 2, ...(open && { display: 'none' }) }}
              >
                <Menu />
              </IconButton>
              <Typography variant="h6" component="h1" noWrap>
                <Link href="/">
                  Agent LLM
                </Link>
              </Typography>
            </Box>
            <MenuDarkSwitch checked={darkMode} onChange={handleToggleDarkMode} />
          </Toolbar>
        </AppBar>
        <Drawer
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              boxSizing: 'border-box',
            },
          }}
          variant="persistent"
          anchor="left"
          open={open}
        >
          <DrawerHeader sx={{ justifyContent: "space-between", pl: "1rem" }}>
            <Typography variant="h6" component="h1" noWrap sx={{ fontWeight: "bold" }}>
              Agents
            </Typography>
            <IconButton onClick={handleDrawerClose}>
              <ChevronLeft fontSize='large' sx={{ color: 'white' }} />
            </IconButton>
          </DrawerHeader>
          <Divider />
          <List>
            <MenuSWR swr={agents} menu={MenuAgentList} />
          </List>
        </Drawer>
        <Main open={open} sx={{ padding: 0 }}>
          <DrawerHeader />
          <Component {...pageProps} />
        </Main>
      </Box>
    </ThemeProvider>
  );
}


