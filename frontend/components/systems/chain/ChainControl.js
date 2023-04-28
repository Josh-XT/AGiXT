import { useRouter } from 'next/router';
import axios from 'axios';
import useSWR from 'swr';
import ChainPanel from './ChainPanel';
import DoubleSidedMenu from '@/components/content/PopoutDrawerWrapper';
import ChainList from './ChainList';
export default function ChainControl({ data }) {
    const chainName = useRouter().query.chain;
    const chains = useSWR('chain', async () => (await axios.get(`${process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:7437'}/api/chain`)).data.chains);
    return <DoubleSidedMenu title={"Manage Chain \""+chainName+"\""} leftHeading={"Chains"} leftSWR={chains} leftMenu={ChainList} rightHeading={null} rightSWR={null} rightMenu={null} content={ChainPanel} />;
}


