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
const Main = styled('main', { shouldForwardProp: (prop) => prop !== 'openLeft' && prop !== 'openRight' })(
    ({ theme, openLeft, openRight }) => ({
        flexGrow: 1,
        padding: theme.spacing(3),
        transition: theme.transitions.create('margin', {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.leavingScreen,
        }),
        ...(openLeft && {
            transition: theme.transitions.create('margin', {
                easing: theme.transitions.easing.easeOut,
                duration: theme.transitions.duration.enteringScreen,
            }),
            marginLeft: `${leftDrawerWidth}px`,
        }),
        ...(openRight && {
            transition: theme.transitions.create('margin', {
                easing: theme.transitions.easing.easeOut,
                duration: theme.transitions.duration.enteringScreen,
            }),
            marginRight: `${rightDrawerWidth}px`,
        }),
    }),
);
const AppBar = styled(MuiAppBar, {
    shouldForwardProp: (prop) => prop !== 'openLeft' && prop !== 'openRight',
})(({ theme, openLeft, openRight }) => ({
    ...(openLeft && {
        width: `calc(100% - ${leftDrawerWidth}px)`,
        marginLeft: `${leftDrawerWidth}px`,
    }),
    ...(openRight && {
        width: `calc(100% - ${rightDrawerWidth}px)`,
        marginRight: `${rightDrawerWidth}px`,
    }),
    ...(openLeft && openRight && {
        width: `calc(100% - ${rightDrawerWidth}px - ${leftDrawerWidth}px)`,
    })
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
    const [openLeft, setOpenLeft] = useState(Boolean(leftHeading));
    const handleDrawerOpenLeft = () => {
        setOpenLeft(true);
    };
    const handleDrawerCloseLeft = () => {
        setOpenLeft(false);
    };
    const [openRight, setOpenRight] = useState(Boolean(rightHeading));
    const handleDrawerOpenRight = () => {
        setOpenRight(true);
    };
    const handleDrawerCloseRight = () => {
        setOpenRight(false);
    };
    const agentName = useRouter().query.agent;
    const commands = useSWR(`agent/${agentName}/commands`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`)).data.commands);
    return (<>
        <AppBar position="relative" openLeft={openLeft} openRight={openRight}>
            <Toolbar sx={{ display: "flex", justifyContent: "space-between" }}>
                {
                    leftHeading
                    ?
                    <Box aria-label="openLeft drawer"
                        onClick={handleDrawerOpenLeft}
                        sx={{ ml: 2, display: "flex", alignItems: "center", cursor: "pointer", ...(openLeft && { display: 'none' }) }}>
                        <Typography variant="h6" component="h1" noWrap>
                            {leftHeading}
                        </Typography>
                        <IconButton color="inherit" edge="start">
                            <ChevronRight />
                        </IconButton>
                    </Box>
                    :
                    null
                }
                {openLeft || !leftHeading ? <span></span> : null}
                <Typography variant="h6" component="h1" noWrap>
                    {title}
                </Typography>
                {openRight || !rightHeading ? <span></span> : null}
                {
                    rightHeading
                    ?
                    <Box aria-label="openRight drawer"
                        onClick={handleDrawerOpenRight}
                        sx={{ mr: 2, display: "flex", alignItems: "center", cursor: "pointer", ...(openRight && { display: 'none' }) }}>
                        <IconButton color="inherit" edge="start">
                            <ChevronLeft />
                        </IconButton>
                        <Typography variant="h6" component="h1" noWrap>
                            {rightHeading}
                        </Typography>
                    </Box>
                    :
                    null
                }
            </Toolbar>
        </AppBar>
        {
            leftHeading
            ?
            <Drawer
                sx={{
                    direction: "rtl",
                    width: leftDrawerWidth,
                    flexShrink: 0,
                    '& .MuiDrawer-paper': {
                        width: leftDrawerWidth,
                        boxSizing: 'border-box',
                        postition: "absolute",
                        top: "4rem",
                        left: "unset",
                    },
                }}
                variant="persistent"
                anchor="left"
                open={openLeft}
            >
                <DrawerHeader color='primary' sx={{ justifyContent: "space-between", px: "1rem", direction: "ltr" }}>
                <Typography variant="h6" component="h1" noWrap >
                        {leftHeading}
                    </Typography>
                    <IconButton onClick={handleDrawerCloseLeft}>
                        <ChevronLeft fontSize='large' sx={{ color: 'white' }} />
                    </IconButton>

                </DrawerHeader>
                <Divider />
                <List sx={{ direction: "ltr" }}>
                    <MenuSWR swr={leftSWR} menu={leftMenu} />
                </List></Drawer>
            :
            null
        }
        {
            rightHeading
            ?
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
                open={openRight}
            >
                <DrawerHeader color='primary' sx={{ justifyContent: "space-between", px: "1rem" }}>
                    
                    <IconButton onClick={handleDrawerCloseRight}>
                        <ChevronRight fontSize='large' sx={{ color: 'white' }} />
                    </IconButton>
                    <Typography variant="h6" component="h1" noWrap >
                        {rightHeading}
                    </Typography>
                </DrawerHeader>
                <Divider />
                <List>
                    <MenuSWR swr={rightSWR} menu={rightMenu} />
                </List>
            </Drawer>
            :
            null
        }
        <Main openLeft={openLeft} openRight={openRight}   >
            {content()}
        </Main>
    </>);
}


