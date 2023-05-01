import {
    Drawer,
    List,
    Typography,
    Divider,
    IconButton
} from '@mui/material';
import { styled } from '@mui/material/styles';
import {
    ChevronRight,
    ChevronLeft
} from '@mui/icons-material';
import MenuSWR from '@/components/data/MenuSWR';
export default function PopoutDrawer({ open, handleClose, side, width, heading, menu, swr }) {
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
    return <Drawer
        sx={{
            direction: side === "left" ? "rtl" : "ltr",
            width: width,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
                width: width,
                boxSizing: 'border-box',
                postition: "absolute",
                top: "4rem",
                left: "unset",
            },
        }}
        variant="persistent"
        anchor={side}
        open={open}
    >
        <DrawerHeader color='primary' sx={{ justifyContent: "space-between", px: "1rem", direction: "ltr" }}>
            {
                side == "left"
                    ?
                    <IconButton onClick={handleClose}>
                        <ChevronLeft fontSize='large' sx={{ color: 'white' }} />
                    </IconButton>
                    :
                    null
            }
            <Typography variant="h6" component="h1" noWrap >
                {heading}
            </Typography>
            {
                side == "right"
                    ?
                    <IconButton onClick={handleClose}>
                        <ChevronRight fontSize='large' sx={{ color: 'white' }} />
                    </IconButton>
                    :
                    null
            }
        </DrawerHeader>
        <Divider />
        <List sx={{ direction: "ltr" }}>
            <MenuSWR swr={swr} menu={menu} />
        </List>
    </Drawer>
}