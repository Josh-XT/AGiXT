import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ChainPanel from './ChainPanel';
import DoubleSidedMenu from '@/components/content/DoubleSidedMenu';
import ChainList from './ChainList';
export default function AgentControl({ data }) {
    const chainName = useRouter().query.agent;
    const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data.chains);
    return <DoubleSidedMenu title={"Manage Chain \""+chainName+"\""} leftHeading={"Agents"} leftSWR={chains} leftMenu={ChainList} rightHeading={null} rightSWR={null} rightMenu={null} content={ChainPanel} />;
}


