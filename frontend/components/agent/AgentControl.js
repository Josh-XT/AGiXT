import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import AgentPanel from './AgentPanel';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import AgentCommandsList from './AgentCommandList';
import MenuAgentList from './AgentList';
export default function AgentControl({ data }) {
    const agentName = useRouter().query.agent;
    const commands = useSWR(`agent/${agentName}/commands`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent/${agentName}/command`)).data.commands);
    const agents = useSWR('agents', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:5000'}/api/agent`)).data.agents);
    return <DoubleSidedMenu title={"Control Agent \""+agentName+"\""} leftHeading={"Agents"} leftSWR={agents} leftMenu={MenuAgentList} rightHeading={`${agentName} Commands`} rightSWR={commands} rightMenu={AgentCommandsList} content={AgentPanel} />;
}


