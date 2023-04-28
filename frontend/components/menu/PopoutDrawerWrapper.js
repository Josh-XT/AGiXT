import { useState } from 'react';
import {
    Toolbar,
    Typography
} from '@mui/material';
import MuiAppBar from '@mui/material/AppBar';
import { styled } from '@mui/material/styles';
import PopoutDrawer from './PopoutDrawer';
import PopoutDrawerWrapperAppBarButton from './PopoutDrawerWrapperAppBarButton';
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
export default function PopoutDrawerWrapper({ title, leftHeading, leftSWR, leftMenu, rightHeading, rightSWR, rightMenu, children }) {
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
    return (<>
        <AppBar position="relative" openLeft={openLeft} openRight={openRight}>
            <Toolbar sx={{ display: "flex", justifyContent: "space-between" }}>
                <PopoutDrawerWrapperAppBarButton open={openLeft} handleOpen={handleDrawerOpenLeft} side="left" heading={leftHeading} />
                <Typography variant="h6" component="h1" noWrap>
                    {title}
                </Typography>
                <PopoutDrawerWrapperAppBarButton open={openRight} handleOpen={handleDrawerOpenRight} side="right" heading={rightHeading} />
            </Toolbar>
        </AppBar>
        {leftHeading?<PopoutDrawer side="left" width={leftDrawerWidth} open={openLeft} handleClose={handleDrawerCloseLeft} heading={leftHeading} menu={leftMenu} swr={leftSWR} />:null}
        <Main openLeft={openLeft} openRight={openRight}>
            {children}
        </Main>
        {rightHeading?<PopoutDrawer side="right" width={rightDrawerWidth} open={openRight} handleClose={handleDrawerCloseRight} heading={rightHeading} menu={rightMenu} swr={rightSWR}/>:null}
    </>);
}


