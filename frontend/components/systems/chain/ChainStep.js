
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr";
import useSWR from "swr";
import {
    Typography,
    Paper,
    MenuItem,
    TextField,
    Input,
    Button,
    IconButton,
    Box,
    Select,
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Avatar,
} from "@mui/material";
import {
    ArrowCircleUp,
    ArrowCircleDown,
    AddCircleOutline,
    HighlightOff,
    ExpandCircleDownOutlined,
    InsertLink,
    LowPriority
} from '@mui/icons-material';
export default function ChainStep({ stepNum, updateCallback }) {
    const [running, setRunning] = useState(false);
    /*
    const agentName = useRouter().query.agent;
    const taskStatus = useSWR(`agent/${agentName}/task`, async () => (running ? (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`)).data.output.split("\n") : null), { refreshInterval: running ? 3000 : 0, revalidateOnFocus: false });
    const queryRunning = useCallback(async () => {
        setRunning((await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task/status`)).data.status, { objective: objective });
    }, [agentName]);
    useEffect(() => {
        queryRunning();
    }, [queryRunning])

    const toggleRunning = async () => {
        if (running) {
            await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`, { objective: "" });
        }
        else {
            await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`, { objective: objective });
        }
        await queryRunning();
        mutate("agents");
    };
    console.log(taskStatus.data);
    */

    const [expanded, setExpanded] = useState(false);

    const handleChange = () => {
      setExpanded(old => !old);
    };
    return (
        <>
            <Paper elevation={5} sx={{ padding: "0.5rem", display: "flex", flexDirection: "column", my: "1rem", fontSize: "1rem" }}>
                <Accordion expanded={expanded} onChange={handleChange}>
                    <AccordionSummary sx={{ flexDirection: "row-reverse", alignItems: "center" }} expandIcon={<ExpandCircleDownOutlined />}>
                        <Box  sx={{ display: "flex", justifyContent: "center", alignItems: "center", mx: "0.5rem"}}>
                            {expanded?null:<Typography variant="h6" sx={{mr:"2rem"}}>Step Inputs</Typography>}
                            <Box onClick={(e) => {e.stopPropagation()}} sx={{ display: "flex", justifyContent: "center", alignItems: "center"}}>
                            <IconButton size="large"><ArrowCircleUp sx={{ fontSize: "2rem" }} /></IconButton>
                            <Avatar sx={{ fontWeight: "bolder" }}>{stepNum}</Avatar>
                            <IconButton size="large"><ArrowCircleDown sx={{ fontSize: "2rem" }} /></IconButton>
                            <Select label="Agent" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>Select an Agent...</MenuItem>
                            </Select>
                            <Select label="Prompt" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>Select a Prompt...</MenuItem>
                            </Select>
                            <Select label="Save Output In" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>Select an Output Save Location...</MenuItem>
                            </Select>
                            <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                            </Box>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        {expanded?<Typography variant="h6">Step Inputs</Typography>:null}
                        <Paper elevation={3} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", my: "0.5rem", mx: "2rem", p: "0.3rem" }}>
                            <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                            <Select label="Type" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>Select an Input Type...</MenuItem>
                            </Select>
                        </Paper>
                        <Paper elevation={3} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", my: "0.5rem", mx: "2rem", p: "0.3rem" }}>
                            <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                            <Select label="Type" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>Saved Output</MenuItem>
                            </Select>
                            <Select label="Output" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>&quot;Step 3 Output&quot;</MenuItem>
                            </Select>
                            <TextField variant="outlined" value="{step3}"></TextField>
                        </Paper>
                        <Paper elevation={3} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", my: "0.5rem", mx: "2rem", p: "0.3rem" }}>
                            <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                            <Select label="Type" sx={{ mx: "0.5rem" }} value={0}>
                                <MenuItem value={0}>Literal Value</MenuItem>
                            </Select>
                            <TextField variant="outlined" value="console.log('Hello, World!');"></TextField>
                            <TextField variant="outlined" value="{myLiteral}"></TextField>
                        </Paper>
                    </AccordionDetails>
                </Accordion>

            </Paper>


        </>
    );
};
