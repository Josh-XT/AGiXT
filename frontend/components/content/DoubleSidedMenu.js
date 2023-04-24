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
import MenuSWR from '@/components/menu/MenuSWR';
const leftDrawerWidth = 320;
const rightDrawerWidth = 320;
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
            marginRight: `${rightDrawerWidth}px`,
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
        width: `calc(100% - ${rightDrawerWidth}px)`,
        marginRight: `${rightDrawerWidth}px`,
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
export default function AgentControl({ title, leftHeading, leftSWR, leftMenu, rightHeading, rightSWR, rightMenu, content }) {
    const [open, setOpen] = useState(false);
    const handleDrawerOpen = () => {
        setOpen(true);
    };
    const handleDrawerClose = () => {
        setOpen(false);
    };
    const agentName = useRouter().query.agent;
    const commands = useSWR(`agent/${agentName}/commands`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`)).data.commands);
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
                width: rightDrawerWidth,

                flexShrink: 0,
                '& .MuiDrawer-paper': {
                    width: rightDrawerWidth,
                    boxSizing: 'border-box',
                    postition: "absolute",
                    top: "4rem"
                },

            }}
            variant="persistent"
            anchor="right"
            open={open}
        >
            <Drawer
                sx={{
                    width: leftDrawerWidth,

                    flexShrink: 0,
                    '& .MuiDrawer-paper': {
                        width: leftDrawerWidth,
                        boxSizing: 'border-box',
                        postition: "absolute",
                        top: "4rem"
                    },

                }}
                variant="persistent"
                anchor="left"
                open={open}
            ><DrawerHeader color='primary' sx={{ justifyContent: "space-between", pl: "1rem" }}>
                    <Typography variant="h6" component="h1" noWrap >
                        {rightHeading}
                    </Typography>
                    <IconButton onClick={handleDrawerClose}>
                        <ChevronRight fontSize='large' sx={{ color: 'white' }} />
                    </IconButton>
                </DrawerHeader>
                <Divider />
                <List>
                    <MenuSWR swr={rightSWR} menu={rightMenu} />
                </List></Drawer>
            <DrawerHeader color='primary' sx={{ justifyContent: "space-between", pl: "1rem" }}>
                <Typography variant="h6" component="h1" noWrap >
                    {rightHeading}
                </Typography>
                <IconButton onClick={handleDrawerClose}>
                    <ChevronRight fontSize='large' sx={{ color: 'white' }} />
                </IconButton>
            </DrawerHeader>
            <Divider />
            <List>
                <MenuSWR swr={rightSWR} menu={rightMenu} />
            </List>
        </Drawer>
        <Main open={open}   >
            {content()}
        </Main>
    </>);
}


