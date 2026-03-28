from datetime import datetime
import json
import os

class ProjectManager:
    """项目管理类，用于管理测试项目"""
    
    def __init__(self, projects_dir="projects"):
        """初始化项目管理器
        Args:
            projects_dir: 项目保存目录
        """
        self.projects_dir = projects_dir
        self.projects = []

        # 确保项目目录存在
        os.makedirs(self.projects_dir, exist_ok=True)

        # 加载已有项目
        self._load_projects()

    def _load_projects(self):
        """从文件加载所有项目"""
        self.projects = []

        if not os.path.exists(self.projects_dir):
            return
        
        for filename in os.listdir(self.projects_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.projects_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        project_data = json.load(f)
                        self.projects.append(project_data)
                except Exception as e:
                    print(f"加载项目文件 {filename} 时出错: {e}")

    def _save_project(self, project_data):
        """保存单个项目到文件"""
        # 使用项目名称和时间戳创建文件名
        safe_name = project_data['project_name'].replace(' ', '_').replace('/', '_')
        timestamp = project_data['created_at'].replace(' ', '_').replace(':', '')
        filename = f"{safe_name}_{timestamp}.json"
        filepath = os.path.join(self.projects_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)

    def add_project(self, project_name, test_configs):
        """添加项目并保存到文件

        Args:
            project_name: 项目名称
            test_configs: 测试配置列表
        """
        project_data = {
            'project_name': project_name,
            'test_configs': test_configs,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # 保存到文件
        self._save_project(project_data)

        # 添加到内存列表
        self.projects.append(project_data)
        print(f"项目 '{project_name}' 已添加并保存")

    def list_projects(self):
        """列出所有项目"""
        if not self.projects:
            print("没有项目")
            return

        print(f"项目清单 (共{len(self.projects)}个):")
        for i, project in enumerate(self.projects):
            print(f"{i+1}. {project['project_name']} (创建时间: {project['created_at']})")
            print(f"   测试数量: {len(project['test_configs'])}")
            # 只显示前几个测试配置，避免输出过长
            max_display = 3
            for j, test in enumerate(project['test_configs'][:max_display]):
                # 根据测试配置类型显示不同的信息
                freq_mhz = test['frequency'] / 1e6

                # 判断配置类型
                if 'power' in test:
                    # 普通功率扫描配置
                    print(f"   {j+1}. {test['test_name']}: {freq_mhz:.0f}MHz, {test['power']} dBm")
                elif 'start_power' in test:
                    # 最大功率测试配置
                    print(f"   {j+1}. {test['test_name']}: {freq_mhz:.0f}MHz, 起始功率: {test['start_power']} dBm")
                else:
                    # 其他类型的配置
                    print(f"   {j+1}. {test['test_name']}: {freq_mhz:.0f}MHz")
            if len(project['test_configs']) > max_display:
                print(f"   ... 还有 {len(project['test_configs']) - max_display} 个测试点")
            print()

    def get_project(self, index):
        """获取指定索引的项目

        Args:
            index: 项目索引 (从1开始)

        Returns:
            项目数据，如果索引无效则返回None
        """
        if 1 <= index <= len(self.projects):
            return self.projects[index-1]
        return None

    def delete_project(self, index):
        """删除指定项目

        Args:
            index: 项目索引 (从1开始)

        Returns:
            bool: 是否删除成功
        """
        if 1 <= index <= len(self.projects):
            project = self.projects[index-1]

            # 从内存中删除
            del self.projects[index-1]

            # 从文件系统中删除对应的文件
            safe_name = project['project_name'].replace(' ', '_').replace('/', '_')
            timestamp = project['created_at'].replace(' ', '_').replace(':', '')
            filename = f"{safe_name}_{timestamp}.json"
            filepath = os.path.join(self.projects_dir, filename)

            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"项目 '{project['project_name']}' 已删除")
                return True

        print(f"无效的项目索引: {index}")
        return False
