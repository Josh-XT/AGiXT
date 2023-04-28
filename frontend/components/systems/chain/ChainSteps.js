
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/router";
import axios from "axios";
import { mutate } from "swr";
import useSWR from "swr";
import {
    Typography,
    Box,
    IconButton,
} from "@mui/material";
import {
    AddCircleOutline,
    InsertLink,
    LowPriority
} from '@mui/icons-material';
import ChainStep from "./ChainStep";
export default function ChainSteps() {
    /*
    const [running, setRunning] = useState(false);
    const [objective, setObjective] = useState("");
    const agentName = useRouter().query.agent;
    const taskStatus = useSWR(`agent/${agentName}/task`, async () => (running ? (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`)).data.output.split("\n") : null), { refreshInterval: running?3000:0, revalidateOnFocus: false });
    const queryRunning = useCallback(async () => {
        setRunning((await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task/status`)).data.status, {objective: objective});
    }, [agentName]);
    useEffect(() => {
        queryRunning();
    }, [queryRunning])

    const toggleRunning = async () => {
        if (running) {
            await axios.post(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/task`, {objective: "" });
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
            <ChainStep stepNum={1} updateCallback={() => { return null; }} />
            <Box sx={{ display: "flex", justifyContent: "left", alignItems: "center" }}>
                <IconButton>
                    <InsertLink sx={{ fontSize: "2rem" }} />
                </IconButton>
                <Typography variant="h5" sx={{ fontWeight: "bolder", mx: "1rem" }}>Runs Concurrently With</Typography>
            </Box>
            <ChainStep stepNum={2} updateCallback={() => { return null; }} />
            <Box sx={{ display: "flex", justifyContent: "left", alignItems: "center" }}>
                <IconButton>
                    <LowPriority sx={{ fontSize: "2rem" }} />
                </IconButton>
                <Typography variant="h5" sx={{ fontWeight: "bolder", mx: "1rem" }}>Runs Sequentially Before</Typography>
            </Box>
            <ChainStep stepNum={3} updateCallback={() => { return null; }} />
            <Box sx={{ display: "flex", justifyContent: "left", alignItems: "center" }}>
                <IconButton>
                    <AddCircleOutline sx={{ fontSize: "2rem" }} />
                </IconButton>
                <Typography variant="h5" sx={{ fontWeight: "bolder", mx: "1rem" }}>Add Step</Typography>
            </Box>
        </>
    );
};
