
import { useState, useEffect, useCallback, useMemo } from "react";
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
    SaveRounded,
    LowPriority
} from '@mui/icons-material';
import StepTypePrompt from "./step_types/StepTypePrompt";
import StepTypeCommand  from "./step_types/StepTypeCommand";
import StepTypeChain    from "./step_types/StepTypeChain";
import StepTypeTask from "./step_types/StepTypeTask";
import StepTypeInstruction from "./step_types/StepTypeInstruction";
export default function ChainStep({ step_number, last_step, agent_name, prompt_name, prompt_type, prompt, command_name, command_args, chain_name, updateCallback }) {
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
    const [stepType, setStepType] = useState(-1);
    const router = useRouter();
    const [modified, setModified] = useState(false);
    const step_types = useMemo(() => {
        return [
            {name: "prompt", component: <StepTypePrompt agent_name={agent_name} prompt_name={prompt_name} prompt={prompt} />},
            {name: "command", component: <StepTypeCommand prompt={prompt}/>},
            {name: "task", component: <StepTypeTask agent_name={agent_name} prompt={prompt}/>},
            {name: "instruction", component: <StepTypeInstruction agent_name={agent_name} prompt={prompt}/>},
            {name: "chain", component: <StepTypeChain prompt={prompt}/>}
        ]
    }, [agent_name, prompt_name, prompt]);
    useEffect(() => {
        setStepType(step_types.findIndex((step_type) => step_type.name == prompt_type));
    }, [prompt_type, step_types])
    const handleChange = () => {
      setExpanded(old => !old);
    };
    const handleIncrement = () => {
        axios.patch(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${router.query.chain}/step/move`, { old_step_number: step_number, new_step_number: step_number+1 }).then(() => {
            mutate('chain/' + router.query.chain);
        });
    };
    const handleDecrement = () => {
        axios.patch(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${router.query.chain}/step/move`, { old_step_number: step_number, new_step_number: step_number-1 }).then(() => {
            mutate('chain/' + router.query.chain);
        });
    };
    const handleSave = () => {
        axios.put(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${router.query.chain}/step/${step_number}`, {
            chain_name: chain_name,
            command_name: command_name,
            command_args: command_args,
            prompt_name: prompt_name,
            prompt_type: prompt_type,
            prompt: prompt,
            agent_name: agent_name
        }).then(() => {
            mutate('chain/' + router.query.chain);
        });
    };
    const handleDelete = () => {
        axios.delete(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain/${router.query.chain}/step/${step_number}`).then(() => {
            mutate('chain/' + router.query.chain);
        });
    };
    console.log(last_step);
    return (
        <>
            <Paper elevation={5} sx={{ padding: "0.5rem", display: "flex", flexDirection: "column", my: "1rem", fontSize: "1rem" }}>
                <Accordion expanded={expanded} onChange={handleChange}>
                    <AccordionSummary sx={{ flexDirection: "row-reverse", alignItems: "center" }} expandIcon={<ExpandCircleDownOutlined />}>
                        <Box  sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", mx: "0.5rem", flex: 1}}>
                            {expanded?null:<Typography variant="h6" sx={{mr:"2rem"}}>Step Inputs</Typography>}
                            <Box onClick={(e) => {e.stopPropagation()}} sx={{ display: "flex", justifyContent: "flex-start", alignItems: "center", flex: 1}}>
                            <IconButton onClick={handleIncrement} size="large" disabled={step_number==1}><ArrowCircleUp sx={{ fontSize: "2rem" }} /></IconButton>
                            <Avatar sx={{ fontWeight: "bolder" }}>{step_number}</Avatar>
                            <IconButton onClick={handleDecrement} size="large" disabled={last_step}><ArrowCircleDown sx={{ fontSize: "2rem" }} /></IconButton>
                            <Select label="Type" sx={{ mx: "0.5rem" }} value={stepType} onChange={(e) => setStepType(e.target.value)}>
                                <MenuItem value={-1}>Select a Type...</MenuItem>
                                {step_types.map((type, index) => {
                                        return <MenuItem key={index} value={index}>{type.name.replace(/\b\w/g, s => s.toUpperCase())}</MenuItem>;
                                    })}
                            </Select>
                            {stepType!==-1?step_types[stepType].component:null}
                            {modified?<IconButton onClick={handleSave} size="large"><SaveRounded sx={{ fontSize: "2rem" }} /></IconButton>:null}
                            <IconButton onClick={handleDelete} size="large"><HighlightOff sx={{ fontSize: "2rem" }} /></IconButton>
                            </Box>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        {/*
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
                                */}
                        <Typography variant="h6">Coming Soon</Typography>
                    </AccordionDetails>
                </Accordion>

            </Paper>


        </>
    );
};
