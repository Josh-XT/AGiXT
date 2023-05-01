import { useRouter } from 'next/router';
import { useMemo } from 'react';
import axios from 'axios';
import useSWR from 'swr';
import AgentPanel from './AgentPanel';
import PopoutDrawerWrapper from '../../menu/PopoutDrawerWrapper';
import AgentCommandsList from './AgentCommandList';
import MenuAgentList from './AgentList';
export default function AgentControl({ data }) {
    const router = useRouter();
    // TODO: Make sure any references to router.query are done using memo so that renames don't break calls.
    const agentName = useMemo(() => router.query.agent, [router.query.agent]);
    const commands = useSWR(`agent/${agentName}/commands`, async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent/${agentName}/command`)).data.commands);
    const agents = useSWR('agent', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/agent`)).data.agents);
    return <PopoutDrawerWrapper title={"Control Agent \""+agentName+"\""} leftHeading={"Agents"} leftSWR={agents} leftMenu={MenuAgentList} rightHeading={`${agentName} Commands`} rightSWR={commands} rightMenu={AgentCommandsList}>
            <AgentPanel agentName={agentName} data={data} />
        </PopoutDrawerWrapper>;
}


