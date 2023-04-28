
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
    Avatar,
} from "@mui/material";
import {
    ArrowCircleUp,
    ArrowCircleDown,
    AddCircleOutline,
    HighlightOff,
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
    return (
        <>

            <Paper elevation={5} sx={{ padding: "0.5rem", display: "flex", flexDirection: "column", my: "1rem" }}>
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
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
                <Box>
                    <Box sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", ml: "2rem" }}>
                        <Typography variant="h6">Step Inputs</Typography>
                        <IconButton size="large"><AddCircleOutline sx={{ fontSize: "2rem" }} /></IconButton>
                    </Box>
                    <Paper elevation={3} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", my: "0.5rem", mx: "2rem", p: "1rem" }}>
                        <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                        <Select label="Type" sx={{ mx: "0.5rem" }} value={0}>
                            <MenuItem value={0}>Select an Input Type...</MenuItem>
                        </Select>
                    </Paper>
                    <Paper elevation={3} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", my: "0.5rem", mx: "2rem", p: "1rem" }}>
                        <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                        <Select label="Type" sx={{ mx: "0.5rem" }} value={0}>
                            <MenuItem value={0}>Saved Output</MenuItem>
                        </Select>
                        <Select label="Output" sx={{ mx: "0.5rem" }} value={0}>
                            <MenuItem value={0}>&quot;Step 3 Output&quot;</MenuItem>
                        </Select>
                        <TextField variant="outlined" value="{step3}"></TextField>
                    </Paper>
                    <Paper elevation={3} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", my: "0.5rem", mx: "2rem", p: "1rem" }}>
                        <IconButton size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                        <Select label="Type" sx={{ mx: "0.5rem" }} value={0}>
                            <MenuItem value={0}>Literal Value</MenuItem>
                        </Select>
                        <TextField variant="outlined" value="console.log('Hello, World!');"></TextField>
                        <TextField variant="outlined" value="{myLiteral}"></TextField>
                    </Paper>
                </Box>
            </Paper>


        </>
    );
};
