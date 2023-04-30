import {
    Box,
    Typography,
    IconButton
} from '@mui/material';
import {
    ChevronRight,
    ChevronLeft
} from '@mui/icons-material';

export default function PopoutDrawerWrapperAppBarButton({ open, handleOpen, side, heading }) {
    return (<>
        {open || !heading
            ?
            <span></span>
            :
            (
                heading
                    ?
                    <Box aria-label="open drawer"
                        onClick={handleOpen}
                        sx={{ ml: 2, display: "flex", alignItems: "center", cursor: "pointer", ...(open && { display: 'none' }) }}>
                        {side === "right" ?
                            <IconButton color="inherit" edge="start" sx={{ml: "0.2rem"}}>
                                <ChevronLeft />
                            </IconButton>
                            : null}
                        <Typography variant="h6" component="h1" noWrap>
                            {heading}
                        </Typography>
                        {side === "left" ?
                            <IconButton color="inherit" edge="start" sx={{ml: "0.2rem"}}>
                                <ChevronRight />
                            </IconButton>
                            : null}
                    </Box>
                    :
                    null
            )
        }
    </>);
}


