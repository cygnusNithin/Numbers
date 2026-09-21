import React, { useState } from 'react';
import { Database, Zap, Shield, TrendingUp, CheckCircle, XCircle, BarChart3, Table } from 'lucide-react';

const LotteryDataInfographic = () => {
  const [activeTab, setActiveTab] = useState('comparison');
  
  // Parse the CSV data
  const rawData = `Roller1,Roller2,Roller3,Roller4,Roller5,Roller6,Roller7,Roller8,Roller9,Roller10,Roller11,Roller12,Roller13,Roller14,Roller15,Roller16,Roller17,Roller18
0850,6870,6716,2082,1983,6875,7457,4578,5748,0045,3407,3885,8615,2786,2766,6966,6698,9989
8597,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN
9710,5276,5900,6501,9014,2386,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN
0142,6962,3312,1213,5493,1621,2577,6487,3627,1675,3646,7417,7483,1530,0316,6060,6989,9769
0431,5815,7171,5270,6152,9671,2971,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN
3031,4019,3198,7769,0537,0650,5804,0730,4045,4610,0961,0141,0414,0452,0179,4536,5607,1642
2061,0782,0522,0832,2095,3803,0426,0034,0374,8605,3421,0371,8700,0269,8707,8614,7180,0054
3740,0669,8500,2530,4788,2012,8085,3535,8816,9550,7403,0093,0762,8963,5301,6898,7943,7951
5687,8621,0518,0354,1039,4583,NaN,0678,3577,1727,9285,8096,0684,4301,5954,8791,9240,NaN
9626,0728,3497,2121,9776,4627,7596,NaN,8608,2204,0354,2613,0486,0261,0413,7230,7107,9924
8247,1510,3820,3876,2597,5940,3917,2771,9664,0007,0597,5854,4598,0290,4419,5468,7507,6173
8274,6079,5478,0841,0062,0041,0062,0031,7957,6002,2622,1622,6226,1905,2083,6152,6083,7418
5843,4579,2422,3703,0800,7272,1721,2492,9728,0770,7539,1918,2891,0210,4821,3614,3658,1681`;

  const lines = rawData.trim().split('\n');
  const headers = lines[0].split(',');
  const dataRows = lines.slice(1).map(line => line.split(','));

  return (
    <div className="w-full max-w-6xl mx-auto p-6 bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-slate-800 mb-2">Lottery Data Storage</h1>
        <p className="text-slate-600">Database Comparison & Data Visualization</p>
        <p className="text-sm text-slate-500 mt-2">1500 Days • ~351,000 Records • ~50MB Total</p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 mb-6 bg-white rounded-lg p-1 shadow-sm">
        <button
          onClick={() => setActiveTab('comparison')}
          className={`flex-1 py-3 px-4 rounded-md font-medium transition-all ${
            activeTab === 'comparison'
              ? 'bg-blue-600 text-white shadow-md'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Database className="inline mr-2 h-5 w-5" />
          Comparison
        </button>
        <button
          onClick={() => setActiveTab('visualization')}
          className={`flex-1 py-3 px-4 rounded-md font-medium transition-all ${
            activeTab === 'visualization'
              ? 'bg-blue-600 text-white shadow-md'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <BarChart3 className="inline mr-2 h-5 w-5" />
          Data Sample
        </button>
      </div>

      {/* Comparison View */}
      {activeTab === 'comparison' && (
        <div className="space-y-6">
          {/* Winner Recommendation */}
          <div className="bg-gradient-to-r from-green-500 to-green-600 text-white p-6 rounded-xl shadow-lg">
            <div className="flex items-start gap-4">
              <div className="bg-white/20 p-3 rounded-lg">
                <CheckCircle className="h-8 w-8" />
              </div>
              <div>
                <h2 className="text-2xl font-bold mb-2">Recommendation: PostgreSQL</h2>
                <p className="text-green-50">
                  Best choice for structured, historical lottery data with complex queries and data integrity requirements
                </p>
              </div>
            </div>
          </div>

          {/* Detailed Comparison Grid */}
          <div className="grid md:grid-cols-2 gap-6">
            {/* PostgreSQL Card */}
            <div className="bg-white rounded-xl shadow-lg overflow-hidden border-2 border-green-500">
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 p-6 text-white">
                <h3 className="text-2xl font-bold mb-2">PostgreSQL/MySQL</h3>
                <p className="text-blue-100">Relational Database</p>
              </div>
              
              <div className="p-6 space-y-4">
                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Perfect Data Structure</p>
                    <p className="text-sm text-slate-600">Fixed schema (18 rollers, consistent rows) fits perfectly</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Complex Queries</p>
                    <p className="text-sm text-slate-600">Easy to find duplicates, analyze patterns, join data</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Data Integrity</p>
                    <p className="text-sm text-slate-600">ACID compliance, constraints prevent bad data</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Storage Efficiency</p>
                    <p className="text-sm text-slate-600">~30-40MB for 1500 days with proper normalization</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Analytics Ready</p>
                    <p className="text-sm text-slate-600">Built-in aggregation, windowing functions</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <XCircle className="h-5 w-5 text-red-500 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Schema Changes</p>
                    <p className="text-sm text-slate-600">Requires migrations if structure changes</p>
                  </div>
                </div>
              </div>

              <div className="bg-slate-50 p-4 border-t">
                <p className="text-sm font-mono text-slate-700">
                  <span className="font-bold">Use Case:</span> Historical analysis, reporting, compliance
                </p>
              </div>
            </div>

            {/* MongoDB Card */}
            <div className="bg-white rounded-xl shadow-lg overflow-hidden">
              <div className="bg-gradient-to-r from-green-600 to-green-700 p-6 text-white">
                <h3 className="text-2xl font-bold mb-2">MongoDB</h3>
                <p className="text-green-100">Document Database</p>
              </div>
              
              <div className="p-6 space-y-4">
                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Flexible Schema</p>
                    <p className="text-sm text-slate-600">Easy to add new fields without migrations</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">JSON-Like Storage</p>
                    <p className="text-sm text-slate-600">Natural fit for nested metadata</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Horizontal Scaling</p>
                    <p className="text-sm text-slate-600">Better for massive growth (not needed here)</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <XCircle className="h-5 w-5 text-red-500 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Query Complexity</p>
                    <p className="text-sm text-slate-600">Harder to do relational joins and aggregations</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <XCircle className="h-5 w-5 text-red-500 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Storage Overhead</p>
                    <p className="text-sm text-slate-600">~50-70MB for same data (more verbose JSON)</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <XCircle className="h-5 w-5 text-red-500 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-slate-800">Data Validation</p>
                    <p className="text-sm text-slate-600">Less strict, requires application-level checks</p>
                  </div>
                </div>
              </div>

              <div className="bg-slate-50 p-4 border-t">
                <p className="text-sm font-mono text-slate-700">
                  <span className="font-bold">Use Case:</span> Rapid prototyping, variable data structures
                </p>
              </div>
            </div>
          </div>

          {/* Performance Metrics */}
          <div className="grid md:grid-cols-3 gap-4">
            <div className="bg-white p-6 rounded-lg shadow-md">
              <div className="flex items-center gap-3 mb-2">
                <Zap className="h-6 w-6 text-yellow-500" />
                <h4 className="font-bold text-slate-800">Query Speed</h4>
              </div>
              <p className="text-2xl font-bold text-blue-600">PostgreSQL</p>
              <p className="text-sm text-slate-600">Indexed queries: &lt;10ms</p>
            </div>

            <div className="bg-white p-6 rounded-lg shadow-md">
              <div className="flex items-center gap-3 mb-2">
                <Shield className="h-6 w-6 text-blue-500" />
                <h4 className="font-bold text-slate-800">Data Integrity</h4>
              </div>
              <p className="text-2xl font-bold text-blue-600">PostgreSQL</p>
              <p className="text-sm text-slate-600">ACID + Constraints</p>
            </div>

            <div className="bg-white p-6 rounded-lg shadow-md">
              <div className="flex items-center gap-3 mb-2">
                <TrendingUp className="h-6 w-6 text-green-500" />
                <h4 className="font-bold text-slate-800">Scalability</h4>
              </div>
              <p className="text-2xl font-bold text-blue-600">Either Works</p>
              <p className="text-sm text-slate-600">Both handle 50MB easily</p>
            </div>
          </div>
        </div>
      )}

      {/* Data Visualization View */}
      {activeTab === 'visualization' && (
        <div className="space-y-6">
          {/* Data Overview */}
          <div className="bg-white p-6 rounded-xl shadow-lg">
            <h3 className="text-xl font-bold text-slate-800 mb-4 flex items-center gap-2">
              <Table className="h-6 w-6 text-blue-600" />
              Sample Data: 21/01/2026 Draw
            </h3>
            
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-100">
                    <th className="p-2 text-left font-semibold text-slate-700">Row</th>
                    {headers.map((header, i) => (
                      <th key={i} className="p-2 text-center font-semibold text-slate-700">
                        {header.replace('Roller', 'R')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dataRows.map((row, i) => (
                    <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                      <td className="p-2 font-bold text-slate-700">{i + 1}</td>
                      {row.map((cell, j) => (
                        <td
                          key={j}
                          className={`p-2 text-center font-mono ${
                            cell === 'NaN'
                              ? 'text-slate-300 bg-slate-200'
                              : cell === '8500'
                              ? 'text-red-600 font-bold bg-red-50'
                              : 'text-slate-800'
                          }`}
                        >
                          {cell === 'NaN' ? '—' : cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex gap-4 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-red-50 border border-red-200"></div>
                <span className="text-slate-600">Duplicate (8500 - re-rolled)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-slate-200"></div>
                <span className="text-slate-600">Closed Window (NaN)</span>
              </div>
            </div>
          </div>

          {/* Statistics */}
          <div className="grid md:grid-cols-4 gap-4">
            <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white p-6 rounded-lg shadow-md">
              <p className="text-sm opacity-90 mb-1">Total Entries</p>
              <p className="text-3xl font-bold">234</p>
              <p className="text-xs opacity-75 mt-1">per day</p>
            </div>

            <div className="bg-gradient-to-br from-purple-500 to-purple-600 text-white p-6 rounded-lg shadow-md">
              <p className="text-sm opacity-90 mb-1">Valid Numbers</p>
              <p className="text-3xl font-bold">
                {dataRows.flat().filter(c => c !== 'NaN').length}
              </p>
              <p className="text-xs opacity-75 mt-1">this draw</p>
            </div>

            <div className="bg-gradient-to-br from-orange-500 to-orange-600 text-white p-6 rounded-lg shadow-md">
              <p className="text-sm opacity-90 mb-1">Closed Windows</p>
              <p className="text-3xl font-bold">
                {dataRows.flat().filter(c => c === 'NaN').length}
              </p>
              <p className="text-xs opacity-75 mt-1">NaN values</p>
            </div>

            <div className="bg-gradient-to-br from-green-500 to-green-600 text-white p-6 rounded-lg shadow-md">
              <p className="text-sm opacity-90 mb-1">1500 Days Total</p>
              <p className="text-3xl font-bold">351K</p>
              <p className="text-xs opacity-75 mt-1">records (~50MB)</p>
            </div>
          </div>

          {/* Schema Preview */}
          <div className="bg-white p-6 rounded-xl shadow-lg">
            <h3 className="text-xl font-bold text-slate-800 mb-4">PostgreSQL Schema Example</h3>
            <pre className="bg-slate-900 text-green-400 p-4 rounded-lg overflow-x-auto text-sm">
{`CREATE TABLE lottery_draws (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  draw_date DATE NOT NULL,
  row_number SMALLINT NOT NULL,
  roller_number SMALLINT NOT NULL,
  value VARCHAR(4),
  is_duplicate BOOLEAN DEFAULT FALSE,
  replaced_by VARCHAR(4),
  INDEX idx_date (draw_date)
);

-- Example insert
INSERT INTO lottery_draws VALUES
(1, '2026-01-21', 1, 1, '0850', FALSE, NULL),
(2, '2026-01-21', 1, 2, '6870', FALSE, NULL),
(3, '2026-01-21', 8, 3, '8500', TRUE, '0725');`}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};

export default LotteryDataInfographic;