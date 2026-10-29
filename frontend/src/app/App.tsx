import ExplorePage from '../pages/ExplorePage.tsx'
import HomePage from '../pages/HomePage.tsx'
import MethodologyPage from '../pages/MethodologyPage.tsx'
import Layout from './Layout.tsx'
import { useRoute } from './router.ts'

export default function App() {
  const route = useRoute()
  const page =
    route.path === '/explore' ? (
      <ExplorePage initialQuery={route.params.get('q') ?? ''} initialLanguage={route.params.get('lang') ?? ''} />
    ) : route.path === '/methodology' ? (
      <MethodologyPage />
    ) : (
      <HomePage />
    )
  return <Layout path={route.path}>{page}</Layout>
}
