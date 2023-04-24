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
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import MenuSWR from '@/components/menu/MenuSWR';
import AgentCommandsList from './AgentCommandList';
export default function AgentControl({ data }) {
    const agentName = useRouter().query.agent;
    const commands = useSWR(`agent/${agentName}/commands`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`)).data.commands);
    return <DoubleSidedMenu title={"Control Agent &quot;"+agentName+"&quot"} leftHeading={null} leftSWR={null} leftMenu={null} rightHeading={"Commands"} rightSWR={commands} rightMenu={AgentCommandsList} content={AgentPanel} />;
}


