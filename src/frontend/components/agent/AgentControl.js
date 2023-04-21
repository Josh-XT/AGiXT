import { useState } from 'react';
import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import {
    Box,
    Drawer,
    Toolbar,
    List,
    Typography,
    Divider,
    IconButton
} from '@mui/material';
import MuiAppBar from '@mui/material/AppBar';
import { styled } from '@mui/material/styles';
import { 
    ChevronRight, 
    ChevronLeft 
} from '@mui/icons-material';
import AgentPanel from './AgentPanel';
import AgentCommandList from './AgentCommandList';
import MenuSWR from '@/components/menu/MenuSWR';
const drawerWidth = 320;
const Main = styled('main', { shouldForwardProp: (prop) => prop !== 'open' })(
    ({ theme, open }) => ({
        flexGrow: 1,
        padding: theme.spacing(3),
        transition: theme.transitions.create('margin', {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.leavingScreen,
        }),
        ...(open && {
            transition: theme.transitions.create('margin', {
                easing: theme.transitions.easing.easeOut,
                duration: theme.transitions.duration.enteringScreen,
            }),
            marginRight: `${drawerWidth}px`,
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
        marginRight: `${drawerWidth}px`,
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
export default function AgentControl({ data }) {
    const [open, setOpen] = useState(false);
    const handleDrawerOpen = () => {
        setOpen(true);
    };
    const handleDrawerClose = () => {
        setOpen(false);
    };
    const agentName = useRouter().query.agent;
    const commands = useSWR(`agent/${agentName}/commands`, async () => (await axios.get(`${process.env.API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`)).data.commands);
    return (<>
        <AppBar position="relative" open={open}>
            <Toolbar sx={{ display: "flex", justifyContent: "space-between" }}>

                <Typography variant="h6" component="h1" noWrap>
                    Control Agent &quot;{agentName}&quot;
                </Typography>
                <Box aria-label="open drawer"
                    onClick={handleDrawerOpen}
                    sx={{ mr: 2, display: "flex", alignItems: "center", cursor: "pointer", ...(open && { display: 'none' }) }}>

                    <IconButton
                        color="inherit"

                        edge="start"

                    >
                        <ChevronLeft />
                    </IconButton>
                    <Typography variant="h6" component="h1" noWrap>
                        Commands
                    </Typography>
                </Box>


            </Toolbar>
        </AppBar>
        <Drawer
            sx={{
                width: drawerWidth,

                flexShrink: 0,
                '& .MuiDrawer-paper': {
                    width: drawerWidth,
                    boxSizing: 'border-box',
                    postition: "absolute",
                    top: "4rem"
                },

            }}
            variant="persistent"
            anchor="right"
            open={open}
        >
            <DrawerHeader color='primary' sx={{ justifyContent: "space-between", pl: "1rem" }}>
                <Typography variant="h6" component="h1" noWrap >
                    Commands
                </Typography>
                <IconButton onClick={handleDrawerClose}>
                    <ChevronRight fontSize='large' sx={{ color: 'white' }} />
                </IconButton>
            </DrawerHeader>
            <Divider />
            <List>
                <MenuSWR swr={commands} menu={AgentCommandList} />
            </List>
        </Drawer>
        <Main open={open}   >
            <AgentPanel />
        </Main>
    </>);
}


