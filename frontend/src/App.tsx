import { Route, Routes } from 'react-router-dom'
import Navbar from '@/components/layout/Navbar'
import Footer from '@/components/layout/Footer'
import Home from '@/pages/Home'
import Analyze from '@/pages/Analyze'
import Analysis from '@/pages/Analysis'
import Story from '@/pages/Story'
import NotFound from '@/pages/NotFound'
import { useLanguage } from '@/hooks/useLanguage'
import { useTheme } from '@/hooks/useTheme'

export default function App() {
  const { language, setLanguage } = useLanguage()
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="flex min-h-screen flex-col bg-parchment transition-colors duration-300">
      <Navbar language={language} onLanguageChange={setLanguage} theme={theme} onThemeToggle={toggleTheme} />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route
            path="/analysis/:analysisId"
            element={<Analysis language={language} onLanguageChange={setLanguage} />}
          />
          <Route
            path="/story/:analysisId"
            element={<Story language={language} onLanguageChange={setLanguage} />}
          />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
