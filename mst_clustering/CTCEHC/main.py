import networkx as nx
import numpy as np
from scipy.spatial.distance import pdist, squareform
import warnings


class CTCEHC:
    def __init__(self, n_clusters=2):
        self.K = n_clusters
        self.mst = None
        self.labels = None
        self.small_tree = None
        self.kprim = None
        self.kprimprim = None
        self.n = None

    def __preliminary_partition(self, data):
        def __recurse(cur_center, cur_neigb):
            if self.labels[cur_neigb] != -1:
                return
            if not weights[tuple(sorted([cur_center, cur_neigb]))] == min(
                [
                    weights[tuple(sorted([neigb_neigb, cur_neigb]))]
                    for neigb_neigb in self.mst[cur_neigb]
                ]
            ):
                return
            self.labels[cur_neigb] = self.labels[cur_center]
            for neigb in self.mst[cur_neigb]:
                __recurse(cur_neigb, neigb)

        self.n = data.shape[0]
        self.mst = self.__emst(data)
        nodes = sorted(self.mst.degree, key=lambda x: x[1], reverse=True)
        self.kprim = 0
        self.labels = np.repeat(-1, self.n)
        i = 0
        weights = nx.get_edge_attributes(self.mst, "bw")
        while any(self.labels < 0):
            xi = nodes[i][0]
            i += 1
            if self.labels[xi] >= 0:
                continue
            self.labels[xi] = self.kprim
            self.kprim += 1
            for xj in self.mst[xi]:
                __recurse(xi, xj)

    def __inter_cluster_distance(self, c1, c2) -> float:
        subgraph1 = self.mst.subgraph(np.arange(self.n)[self.labels == c1])
        subgraph2 = self.mst.subgraph(np.arange(self.n)[self.labels == c2])

        centroid1 = self.__find_centroid(subgraph1)
        centroid2 = self.__find_centroid(subgraph2)

        assert self.labels[centroid1] != self.labels[centroid2]
        sp = nx.shortest_path(self.mst, source=centroid1, target=centroid2, weight="bw")
        path_edges = list(zip(sp[:-1], sp[1:]))
        s = sum([self.mst.edges[e[0], e[1]]["bw"] for e in path_edges])
        return s

    def __generate_small_tree(self):
        G = nx.empty_graph()
        for e in self.mst.edges:
            if self.labels[e[0]] != self.labels[e[1]]:
                u = self.labels[e[0]]
                v = self.labels[e[1]]
                G.add_edge(u, v, weight=self.mst.edges[e[0], e[1]]["bw"])
        return G

    def __cut_edge_contraint_I(self, c1, c2):
        subgraph1 = self.mst.subgraph(np.nonzero(self.labels == c1)[0])
        subgraph2 = self.mst.subgraph(np.nonzero(self.labels == c2)[0])

        weights1 = nx.get_edge_attributes(subgraph1, "bw").values()
        weights2 = nx.get_edge_attributes(subgraph2, "bw").values()

        return self.small_tree.edges[c1, c2]["bw"] <= max(weights1, default=0) + max(
            weights2, default=0
        )

    def __cut_edge_constrait_II(self, c1, c2):
        subgraph1 = self.mst.subgraph(np.nonzero(self.labels == c1)[0])
        subgraph2 = self.mst.subgraph(np.nonzero(self.labels == c2)[0])

        weights1 = nx.get_edge_attributes(subgraph1, "bw").values()
        weights2 = nx.get_edge_attributes(subgraph2, "bw").values()

        return self.small_tree.edges[c1, c2]["bw"] <= min(
            max(weights1, default=0), max(weights2, default=0)
        )

    def small_subcluster_merging(self):
        self.kprimprim = self.kprim
        clusters, counts = np.unique(self.labels, return_counts=True)

        threshold = np.sqrt(self.n)
        self.small_tree = self.__generate_small_tree()
        while np.any(counts <= threshold) and len(clusters) > self.K:
            smallest_cluster_ix = np.argmin(counts)
            smallest_cluster = clusters[smallest_cluster_ix]
            adjacent_clusters = self.small_tree[smallest_cluster]
            adjacent_clusters = sorted(
                adjacent_clusters,
                key=lambda x: self.__inter_cluster_distance(x, smallest_cluster),
            )
            m = len(adjacent_clusters)
            j = 0
            while j < m:
                cur_candidate = adjacent_clusters[j]
                if self.__cut_edge_contraint_I(smallest_cluster, cur_candidate):
                    ixs = self.labels == cur_candidate
                    self.labels[ixs] = smallest_cluster
                    clusters, counts = np.unique(self.labels, return_counts=True)
                    self.small_tree = self.__generate_small_tree()
                    self.kprimprim -= 1
                    break
                else:
                    j += 1
            if j >= m:
                cur_candidate = adjacent_clusters[0]
                ixs = self.labels == cur_candidate
                self.labels[ixs] = smallest_cluster
                clusters, counts = np.unique(self.labels, return_counts=True)
                self.small_tree = self.__generate_small_tree()
                self.kprimprim -= 1

    @staticmethod
    def __emst(data):
        n = data.shape[0]
        G = nx.complete_graph(n)
        pd = squareform(pdist(data))
        edge_weights = {(i, j): pd[i, j] for i in range(n) for j in range(i + 1, n)}
        nx.set_edge_attributes(G, edge_weights, name="bw")
        mst = nx.minimum_spanning_tree(G)

        return mst

    @staticmethod
    def __find_centroid(cluster_tree):
        for node in cluster_tree:
            temp = nx.restricted_view(cluster_tree, [node], [])
            is_centroid = True
            for cc in nx.connected_components(temp):
                if len(cc) > cluster_tree.number_of_nodes() / 2:
                    is_centroid = False
                    break
            if is_centroid:
                return node

    def final_clustering(self):
        distances = {
            (e[0], e[1]): self.__inter_cluster_distance(e[0], e[1])
            for e in self.small_tree.edges
        }
        while self.kprimprim > self.K and any(
            map(
                lambda e: self.__cut_edge_constrait_II(e[0], e[1]),
                self.small_tree.edges,
            )
        ):

            c1, c2 = min(distances.keys(), key=lambda x: distances[x])

            self.labels[(self.labels - c2) == 0] = c1

            self.small_tree = self.__generate_small_tree()

            distances = {
                (e[0], e[1]): self.__inter_cluster_distance(e[0], e[1])
                for e in self.small_tree.edges
            }
            self.kprimprim -= 1

    @staticmethod
    def warn_decor(func, labels, K, kprim, *args, **kwargs):
        func(*args, **kwargs)
        if len(np.unique(labels)) < K:
            warnings.warn(f"Produced {kprim} clusters instead of {K}")
        return

    def __tidy(self):
        uqs = np.unique(self.labels)
        transdict = {uqs[i]: i for i in range(len(uqs))}
        self.labels = np.array([transdict[i] for i in self.labels])
        self.small_tree = self.__generate_small_tree()

    def set_params(self, n_clusters=None):
        if n_clusters is not None:
            self.K = n_clusters

    def fit_predict(self, data):
        self.__preliminary_partition(data)

        if len(np.unique(self.labels)) > self.K:
            self.small_subcluster_merging()
            self.__tidy()
            if len(np.unique(self.labels)) < self.K:
                warnings.warn(f"Produced {self.kprimprim} clusters instead of {self.K}")
                return self.labels, self.mst

        if len(np.unique(self.labels)) > self.K:
            self.final_clustering()
            self.__tidy()
            if len(np.unique(self.labels)) < self.K:
                warnings.warn(f"Produced {self.kprimprim} clusters instead of {self.K}")

        return self.labels
